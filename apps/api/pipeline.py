"""One resumable mailbox page per job invocation; no tokens/content in task messages."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import httpx

from apps.api.domain import HARD_CAP, PolicyError, likely_certificate
from apps.api.pipeline_security import ScannerUnavailable, isolated_extract, scan
from apps.api.providers import (
    GmailAdapter,
    ProviderNotFound,
    ProviderUnavailable,
    TokenCipher,
    refresh_access,
)


class PrivateStorage:
    def __init__(self, client, url, secret):
        self.client, self.url = client, url
        self.headers = {"apikey": secret, "Authorization": "Bearer " + secret}

    async def upload(self, owner, data):
        path = owner + "/" + hashlib.sha256(data).hexdigest() + ".pdf"
        try:
            response = await self.client.post(
                self.url + "/storage/v1/object/certificates/" + path,
                headers={**self.headers, "Content-Type": "application/pdf", "x-upsert": "true"},
                content=data,
                timeout=45,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise ScannerUnavailable("Private storage unavailable") from exc
        if response.status_code not in (200, 201):
            raise ScannerUnavailable("Private storage upload was not confirmed")


def parts(payload):
    """Bounded MIME tree walk; never persist mail HTML or body text."""
    pending = [payload]
    count = 0
    while pending:
        part = pending.pop()
        count += 1
        if count > 200:
            raise PolicyError("Message MIME structure requires review")
        if part.get("filename") and part.get("mimeType") == "application/pdf":
            yield part
        pending.extend(part.get("parts", [])[:200])


async def access(config, store, connection, http):
    cipher = TokenCipher(config.oauth_key.get_secret_value())
    tokens = cipher.decrypt(store.owner, bytes(connection["ciphertext"]))
    if connection["expires_at"] <= datetime.now(UTC) + timedelta(seconds=90):
        tokens = await refresh_access(http, config.oauth(), tokens)
        with store.db() as db:
            db.execute(
                "update private.mailbox_tokens set ciphertext=%s,expires_at=%s where owner_id=%s and connection_id=%s",
                (
                    cipher.encrypt(store.owner, tokens),
                    datetime.now(UTC) + timedelta(seconds=min(tokens.expires_in, 86400)),
                    store.owner,
                    connection["id"],
                ),
            )
    return tokens


async def process_item(
    config, store, connection, item, adapter, storage, threshold, scan_file=None, parse_file=None
):
    if item["status"] not in ("eligible", "downloading", "scanning", "extracting"):
        return
    # Disconnect/approval ownership is checked again before download and final commit.
    active = store.connection(connection["id"])
    if not active or active["state"] != "connected":
        return
    approved = item["approved"]
    store.item_state(item["id"], "downloading")
    try:
        data = await adapter.attachment(
            item["message_id"], item["attachment_id"], threshold, approved
        )
    except PolicyError:
        store.item_state(
            item["id"],
            "rejected" if approved else "awaiting_approval",
            "hard_cap" if approved else "observed_size_exceeded",
        )
        return
    if not data or len(data) > HARD_CAP or not data.startswith(b"%PDF-"):
        store.item_state(item["id"], "needs_review", "unsupported_content")
        return
    store.item_state(item["id"], "scanning")
    try:
        if scan_file:
            scan_file(data)
        else:
            await asyncio.to_thread(scan, data, config.clamd_host, config.clamd_port)
        store.item_state(item["id"], "extracting")
        text = (
            parse_file(data)
            if parse_file
            else await asyncio.to_thread(isolated_extract, data, config.parser_image)
        )
    except PolicyError:
        store.item_state(item["id"], "needs_review", "document_rejected_or_ocr_required")
        return
    # At this point only validated, scanned bytes can leave quarantine for Storage.
    if not store.connection(connection["id"]):
        return
    await storage.upload(store.owner, data)
    store.complete(item, data, text)


async def run_page(config, store, job_id, http, storage, *, scan_file=None, parse_file=None):
    if not config.live_imports_enabled:
        raise ProviderUnavailable("Live mailbox imports are disabled")
    # Session advisory lock covers provider requests without holding row locks/transactions.
    with store.db() as lock:
        row = lock.execute(
            "select * from public.sync_jobs where id=%s and owner_id=%s", (job_id, store.owner)
        ).fetchone()
        if not row or row["status"] in ("completed", "cancelled", "failed"):
            return
        locked = lock.execute(
            "select pg_try_advisory_lock(hashtextextended(%s,0)) as ok",
            (str(row["connection_id"]),),
        ).fetchone()["ok"]
        if not locked:
            return
        try:
            await _page(config, store, row, http, storage, scan_file, parse_file)
        finally:
            lock.execute(
                "select pg_advisory_unlock(hashtextextended(%s,0))", (str(row["connection_id"]),)
            )


async def _page(config, store, job, http, storage, scan_file, parse_file):
    key, connection_id = job["id"], job["connection_id"]
    connection = store.connection(connection_id)
    if not connection or connection["state"] != "connected":
        return
    with store.db() as db:
        db.execute(
            "update public.sync_jobs set status='running',attempts=attempts+1,updated_at=now() where id=%s and owner_id=%s",
            (key, store.owner),
        )
        db.execute(
            "insert into private.pipeline_runs(job_id,owner_id,lease_until) values(%s,%s,now()+interval '5 minutes') on conflict(job_id) do update set lease_until=excluded.lease_until",
            (key, store.owner),
        )
        run = db.execute(
            "select * from private.pipeline_runs where job_id=%s and owner_id=%s",
            (key, store.owner),
        ).fetchone()
        profile = db.execute(
            "select download_limit_bytes from public.profiles where owner_id=%s", (store.owner,)
        ).fetchone()
        pending = db.execute(
            "select * from private.pipeline_items where owner_id=%s and connection_id=%s and status in ('eligible','downloading','scanning','extracting') order by created_at limit 10",
            (store.owner, connection_id),
        ).fetchall()
    threshold = profile["download_limit_bytes"] if profile else 52428800
    tokens = await access(config, store, connection, http)
    adapter = GmailAdapter(http, tokens.access_token)
    work = 0
    for item in pending:
        if work >= 1:
            requeue_page(store, key)
            return
        await process_item(
            config, store, connection, item, adapter, storage, threshold, scan_file, parse_file
        )
        work += 1
    mode = run["mode"] or ("history" if connection["cursor"] else "backfill")
    anchor = run["anchor"] or (await adapter.profile())["historyId"]
    try:
        page = (
            await adapter.history(connection["cursor"], run["page_token"])
            if mode == "history"
            else await adapter.messages(run["page_token"], connection["scan_days"])
        )
    except ProviderNotFound:
        # Expired Gmail history: bounded backfill, deduped by source and hash.
        mode, anchor = "backfill", (await adapter.profile())["historyId"]
        page = await adapter.messages(days=connection["scan_days"])
    with store.db() as db:
        db.execute(
            "update private.pipeline_runs set mode=%s,anchor=%s where job_id=%s and owner_id=%s",
            (mode, anchor, key, store.owner),
        )
    messages = (
        page.get("messages", [])
        if mode == "backfill"
        else [
            entry["message"]
            for event in page.get("history", [])
            for entry in event.get("messagesAdded", [])
        ]
    )
    # History page can contain many changes. Never truncate and advance the cursor.
    if len(messages) > 200:
        raise ProviderUnavailable("History page requires bounded backfill")
    for reference in {m["id"]: m for m in messages}.values():
        try:
            message = await adapter.message(reference["id"])
        except ProviderNotFound:
            continue
        if int(message.get("internalDate", "0")) < int(
            (datetime.now(UTC) - timedelta(days=connection["scan_days"])).timestamp() * 1000
        ):
            continue
        payload = message.get("payload", {})
        subject = next(
            (
                h.get("value", "")
                for h in payload.get("headers", [])
                if h.get("name", "").lower() == "subject"
            ),
            "",
        )
        for part in parts(payload):
            filename, body = part["filename"], part.get("body", {})
            if not likely_certificate(subject, filename):
                continue
            # Inline MIME payloads are deliberately review-only until a streaming adapter exists.
            attachment = body.get("attachmentId")
            if not attachment:
                continue
            size = body.get("size")
            if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
                size = None
            item = store.discover(
                connection_id, reference["id"], attachment, filename, size, threshold
            )
            if item["status"] in ("eligible", "downloading", "scanning", "extracting"):
                if work >= 1:
                    requeue_page(store, key)
                    return
                work += 1
            await process_item(
                config, store, connection, item, adapter, storage, threshold, scan_file, parse_file
            )
    next_page = page.get("nextPageToken")
    with store.db() as db:
        # A disconnect racing this page cannot commit a cursor or revive a cancelled job.
        active = db.execute(
            "select id from public.email_connections where id=%s and owner_id=%s and state='connected' for update",
            (connection_id, store.owner),
        ).fetchone()
        if not active:
            return
        db.execute(
            "update private.pipeline_runs set page_token=%s,anchor=%s,mode=%s,lease_until=null where job_id=%s and owner_id=%s",
            (next_page, anchor, mode, key, store.owner),
        )
        db.execute(
            "update public.sync_jobs set status=%s,attempts=0,safe_error_code=null,updated_at=now() where id=%s and owner_id=%s",
            ("queued" if next_page else "completed", key, store.owner),
        )
        if not next_page:
            # Anchor captured before backfill; history uses the provider's final watermark.
            cursor = page.get("historyId", anchor) if mode == "history" else anchor
            db.execute(
                "update public.email_connections set cursor=%s where id=%s and owner_id=%s",
                (cursor, connection_id, store.owner),
            )
            db.execute(
                "update private.mailbox_tokens set next_poll_at=now()+interval '5 minutes' where connection_id=%s and owner_id=%s",
                (connection_id, store.owner),
            )


def requeue_page(store, job_id):
    # Preserve the page cursor until every candidate has been checkpointed.
    with store.db() as db:
        db.execute(
            "update public.sync_jobs set status='queued',attempts=0,updated_at=now() where id=%s and owner_id=%s and status='running'",
            (job_id, store.owner),
        )
        db.execute(
            "update private.pipeline_runs set lease_until=null where job_id=%s and owner_id=%s",
            (job_id, store.owner),
        )


def fail_job(store, job_id, code, retry=True):
    with store.db() as db:
        db.execute(
            "update public.sync_jobs set status=case when attempts<5 and %s then 'retry' else 'failed' end,safe_error_code=%s,updated_at=now() where id=%s and owner_id=%s and status not in ('cancelled','completed')",
            (retry, code, job_id, store.owner),
        )
        store.notify(
            db,
            "job_error:" + str(job_id),
            "error",
            "An import job needs attention. Check mailbox connection and scanner availability.",
        )
