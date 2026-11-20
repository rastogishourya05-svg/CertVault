"""Transactional ingestion repository, always running as a non-bypass RLS role."""

import hashlib
import json
import uuid
from contextlib import contextmanager

from apps.api.documents import FORMATS, extension, object_path
from apps.api.metadata import extract_metadata
from apps.api.postgres import connect


class PipelineStore:
    def __init__(self, dsn: str, owner: str):
        self.dsn, self.owner = dsn, str(uuid.UUID(owner))

    @contextmanager
    def db(self):
        with connect(self.dsn) as db:
            db.execute("set local role certvault_pipeline")
            db.execute("select set_config('certvault.owner',%s,true)", (self.owner,))
            db.execute("set local statement_timeout='10s'")
            yield db

    def connection(self, key):
        with self.db() as db:
            return db.execute(
                "select c.id,c.owner_id,c.cursor,c.state,m.ciphertext,m.expires_at,m.scan_days,m.automatic "
                "from public.email_connections c join private.mailbox_tokens m "
                "on m.connection_id=c.id and m.owner_id=c.owner_id where c.id=%s and c.owner_id=%s",
                (key, self.owner),
            ).fetchone()

    def connect(self, label, ciphertext, expires, days, automatic):
        with self.db() as db:
            row = db.execute(
                "insert into public.email_connections(owner_id,provider,account_label,scopes,state,consent_at) "
                "values (%s,'gmail',%s,array['https://www.googleapis.com/auth/gmail.readonly'],'connected',now()) "
                "on conflict(owner_id,provider,account_label) do update set state='connected',consent_at=now(),cursor=null returning id",
                (self.owner, label),
            ).fetchone()
            key = row["id"]
            db.execute(
                "insert into private.mailbox_tokens(connection_id,owner_id,ciphertext,expires_at,scan_days,automatic) "
                "values(%s,%s,%s,%s,%s,%s) on conflict(connection_id) do update set "
                "ciphertext=excluded.ciphertext,expires_at=excluded.expires_at,scan_days=excluded.scan_days,automatic=excluded.automatic",
                (key, self.owner, ciphertext, expires, days, automatic),
            )
            self.event(db, "mailbox_connected", key)
            return str(key)

    def event(self, db, action, resource=None):
        db.execute(
            "insert into public.audit_events(owner_id,action,resource_id) values(%s,%s,%s)",
            (self.owner, action, resource),
        )

    def notify(self, db, key, kind, message):
        db.execute(
            "insert into public.notifications(owner_id,event_key,kind,safe_message) values(%s,%s,%s,%s) "
            "on conflict(owner_id,event_key) do nothing",
            (self.owner, key, kind, message),
        )

    def enqueue(self, connection, *, rescan=False):
        with self.db() as db:
            # Serialize enqueue per connection; there is at most one outstanding job.
            row = db.execute(
                "select id from public.email_connections where id=%s and owner_id=%s and state='connected' for update",
                (connection, self.owner),
            ).fetchone()
            if not row:
                raise ValueError("Mailbox not connected")
            job = db.execute(
                "select id,status from public.sync_jobs where owner_id=%s and connection_id=%s and status in ('queued','running','retry') limit 1",
                (self.owner, connection),
            ).fetchone()
            if rescan and job and job["status"] == "retry":
                db.execute(
                    "update public.sync_jobs set status='cancelled',safe_error_code='superseded_by_manual_rescan',updated_at=now() where id=%s and owner_id=%s",
                    (job["id"], self.owner),
                )
                job = None
            if not job:
                if rescan:
                    # Older code used a volatile Gmail download token as source identity.
                    # Preserve history, but retire those pending references on explicit rescan.
                    db.execute(
                        "update private.pipeline_items set status='needs_review',safe_error='legacy_source_reference',updated_at=now() "
                        "where connection_id=%s and owner_id=%s and attachment_id not like 'part:%%' and attachment_id not like 'link:%%' "
                        "and status in ('eligible','downloading','scanning','extracting')",
                        (connection, self.owner),
                    )
                    db.execute(
                        "update private.pipeline_items set status='eligible',safe_error=null,updated_at=now() "
                        "where connection_id=%s and owner_id=%s and status='needs_review' "
                        "and safe_error='document_rejected_or_ocr_required' and attachment_id like 'part:%%'",
                        (connection, self.owner),
                    )
                    db.execute(
                        "update public.email_connections set cursor=null where id=%s and owner_id=%s",
                        (connection, self.owner),
                    )
                job = db.execute(
                    "insert into public.sync_jobs(owner_id,connection_id,idempotency_key) values(%s,%s,%s) returning id",
                    (self.owner, connection, str(uuid.uuid4())),
                ).fetchone()
            return str(job["id"])

    def job_status(self, key):
        with self.db() as db:
            row = db.execute(
                "select status from public.sync_jobs where id=%s and owner_id=%s",
                (key, self.owner),
            ).fetchone()
            return row["status"] if row else None

    def snapshot(self):
        with self.db() as db:

            def rows(sql):
                return db.execute(sql, (self.owner,)).fetchall()

            return {
                "connections": rows(
                    "select c.id,c.account_label,c.state,m.automatic,m.scan_days from public.email_connections c join private.mailbox_tokens m on m.connection_id=c.id where c.owner_id=%s order by c.created_at desc"
                ),
                "jobs": rows(
                    "select j.id,j.status,j.attempts,j.safe_error_code,j.updated_at,r.summary, "
                    "(select coalesce(jsonb_agg(result),'[]'::jsonb) from (select i.certificate_id,i.filename "
                    "from private.scan_items s join private.pipeline_items i on i.id=s.item_id and i.owner_id=s.owner_id "
                    "where s.job_id=j.id and s.owner_id=j.owner_id and s.outcome='stored' and i.certificate_id is not null "
                    "order by i.filename,i.id limit 20) result) as stored_files "
                    "from public.sync_jobs j left join private.pipeline_runs r "
                    "on r.job_id=j.id and r.owner_id=j.owner_id where j.owner_id=%s order by j.created_at desc limit 20"
                ),
                "imports": rows(
                    "select i.id,i.filename,i.declared_bytes,i.status,i.safe_error,i.approved,i.certificate_id from private.pipeline_items i where i.owner_id=%s "
                    "and not (i.attachment_id not like 'part:%%' and exists (select 1 from private.pipeline_items n "
                    "where n.owner_id=i.owner_id and n.connection_id=i.connection_id and n.message_id=i.message_id "
                    "and n.filename=i.filename and n.attachment_id like 'part:%%')) order by i.created_at desc limit 100"
                ),
                "approvals": rows(
                    "select id,filename,status,declared_bytes,safe_error from private.pipeline_items "
                    "where owner_id=%s and status='awaiting_approval' order by created_at"
                ),
                "notifications": rows(
                    "select id,kind,safe_message,read_at from public.notifications where owner_id=%s and read_at is null order by created_at desc limit 20"
                ),
            }

    def decide(self, key, approved):
        with self.db() as db:
            row = db.execute(
                "update private.pipeline_items set approved=%s,status=%s,updated_at=now() "
                "where id=%s and owner_id=%s and status='awaiting_approval' returning connection_id",
                (approved, "eligible" if approved else "rejected", key, self.owner),
            ).fetchone()
            if row:
                self.event(db, "import_approved" if approved else "import_rejected", key)
            return row

    def disconnect(self, connection):
        with self.db() as db:
            row = db.execute(
                "update public.email_connections set state='disconnected',cursor=null where id=%s and owner_id=%s returning id",
                (connection, self.owner),
            ).fetchone()
            if not row:
                return False
            db.execute(
                "delete from private.mailbox_tokens where connection_id=%s and owner_id=%s",
                (connection, self.owner),
            )
            db.execute(
                "update public.sync_jobs set status='cancelled',updated_at=now() where connection_id=%s and owner_id=%s and status in ('queued','running','retry')",
                (connection, self.owner),
            )
            self.event(db, "mailbox_disconnected", connection)
            return True

    def issue_storage_upload(self, object_path):
        """Mint a one-use Storage insert ticket after the file passed scanning."""
        if not object_path.startswith(self.owner + "/") or len(object_path) > 220:
            raise ValueError("Storage path is not owner-scoped")
        with self.db() as db:
            db.execute("delete from private.storage_upload_tickets where expires_at < now()")
            db.execute(
                "insert into private.storage_upload_tickets(owner_id,object_path,expires_at) "
                "values(%s,%s,now()+interval '3 minutes') "
                "on conflict(owner_id,object_path) do update set "
                "expires_at=excluded.expires_at,consumed_at=null",
                (self.owner, object_path),
            )

    def discover(self, connection, message, attachment, filename, size, threshold):
        from apps.api.domain import STORAGE_HARD_CAP, size_decision

        status = size_decision(size, threshold, hard_cap=STORAGE_HARD_CAP)
        safe_error = "storage_size_limit_exceeded" if status == "rejected" else None
        if attachment.startswith("link:"):
            unsupported = filename == "Issuer link requires manual review"
            status = "needs_review" if unsupported else "awaiting_approval"
            safe_error = (
                "unsupported_issuer_page" if unsupported else "issuer_link_requires_approval"
            )
        with self.db() as db:
            row = db.execute(
                "insert into private.pipeline_items(owner_id,connection_id,message_id,attachment_id,filename,declared_bytes,status,safe_error) "
                "values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(owner_id,connection_id,message_id,attachment_id) "
                "do update set filename=private.pipeline_items.filename returning *",
                (
                    self.owner,
                    connection,
                    message,
                    attachment,
                    filename[:160],
                    size,
                    status,
                    safe_error,
                ),
            ).fetchone()
            if row["status"] == "awaiting_approval":
                self.notify(
                    db,
                    "approval:" + str(row["id"]),
                    "approval",
                    "A certificate download needs approval.",
                )
            elif row["status"] == "rejected" and row["safe_error"] == "storage_size_limit_exceeded":
                self.notify(
                    db,
                    "size_limit:" + str(row["id"]),
                    "error",
                    "A certificate exceeds the 50 MB Storage limit. It was not downloaded and cannot be approved.",
                )
            return row

    def item_state(self, key, status, error=None):
        with self.db() as db:
            db.execute(
                "update private.pipeline_items set status=%s,safe_error=%s,updated_at=now() where id=%s and owner_id=%s",
                (status, error, key, self.owner),
            )
            if status == "rejected" and error == "storage_size_limit_exceeded":
                self.notify(
                    db,
                    "size_limit:" + str(key),
                    "error",
                    "A certificate exceeds the 50 MB Storage limit. It was not saved and cannot be approved.",
                )
            elif status in ("needs_review", "failed", "awaiting_approval"):
                self.notify(
                    db,
                    status + ":" + str(key),
                    status,
                    "An import needs your attention. Open import activity for details.",
                )

    def complete(self, item, data, text):
        digest = hashlib.sha256(data).hexdigest()
        with self.db() as db:
            # Serialize same-owner hashes and disconnect vs final commit.
            db.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))", (self.owner + digest,)
            )
            active = db.execute(
                "select id from public.email_connections where id=%s and owner_id=%s and state='connected' for update",
                (item["connection_id"], self.owner),
            ).fetchone()
            if not active:
                raise ValueError("Mailbox disconnected")
            existing = db.execute(
                "select certificate_id from public.certificate_files where owner_id=%s and sha256=%s",
                (self.owner, digest),
            ).fetchone()
            if existing:
                key, status = existing["certificate_id"], "duplicate"
            else:
                key, status = uuid.uuid4(), "stored"
                metadata = extract_metadata(text, item["filename"])
                db.execute(
                    "insert into public.certificates(id,owner_id,title,issuer,recipient,issued_on,category,source,extracted_text,provenance) "
                    "values(%s,%s,%s,%s,%s,%s,%s,'gmail',%s,%s::jsonb)",
                    (
                        key,
                        self.owner,
                        metadata["title"],
                        metadata["issuer"],
                        metadata["recipient"],
                        metadata["issued_on"],
                        metadata["category"],
                        text,
                        json.dumps(metadata["provenance"]),
                    ),
                )
                db.execute(
                    "insert into public.certificate_files(owner_id,certificate_id,object_path,sha256,mime,bytes,scanned_at) values(%s,%s,%s,%s,%s,%s,now())",
                    (
                        self.owner,
                        key,
                        object_path(self.owner, data),
                        digest,
                        FORMATS[extension(data)],
                        len(data),
                    ),
                )
            db.execute(
                "update private.pipeline_items set status=%s,certificate_id=%s,observed_bytes=%s,safe_error=null,updated_at=now() where id=%s and owner_id=%s",
                (status, key, len(data), item["id"], self.owner),
            )
            self.notify(
                db,
                status + ":" + str(key),
                status,
                "A certificate was saved to your private vault."
                if status == "stored"
                else "A duplicate certificate was skipped.",
            )
            self.event(db, "certificate_" + status, key)
            return str(key)

    def find_certificate_hash(self, data):
        digest = hashlib.sha256(data).hexdigest()
        with self.db() as db:
            return db.execute(
                "select certificate_id from public.certificate_files where owner_id=%s and sha256=%s",
                (self.owner, digest),
            ).fetchone()

    def complete_manual(self, filename, data, text):
        digest = hashlib.sha256(data).hexdigest()
        with self.db() as db:
            db.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))", (self.owner + digest,)
            )
            existing = db.execute(
                "select certificate_id from public.certificate_files where owner_id=%s and sha256=%s",
                (self.owner, digest),
            ).fetchone()
            if existing:
                key, status = existing["certificate_id"], "duplicate"
            else:
                key, status = uuid.uuid4(), "stored"
                metadata = extract_metadata(text, filename)
                db.execute(
                    "insert into public.certificates(id,owner_id,title,issuer,recipient,issued_on,category,source,extracted_text,provenance) "
                    "values(%s,%s,%s,%s,%s,%s,%s,'manual',%s,%s::jsonb)",
                    (
                        key,
                        self.owner,
                        metadata["title"],
                        metadata["issuer"],
                        metadata["recipient"],
                        metadata["issued_on"],
                        metadata["category"],
                        text,
                        json.dumps(metadata["provenance"]),
                    ),
                )
                db.execute(
                    "insert into public.certificate_files(owner_id,certificate_id,object_path,sha256,mime,bytes,scanned_at) "
                    "values(%s,%s,%s,%s,%s,%s,now())",
                    (
                        self.owner,
                        key,
                        object_path(self.owner, data),
                        digest,
                        FORMATS[extension(data)],
                        len(data),
                    ),
                )
            self.notify(
                db,
                status + ":" + str(key),
                status,
                "A certificate was added to your private vault. Review the extracted details."
                if status == "stored"
                else "This certificate was already in your vault; the duplicate was skipped.",
            )
            self.event(db, "certificate_" + status, key)
            return {"certificate_id": str(key), "status": status}
