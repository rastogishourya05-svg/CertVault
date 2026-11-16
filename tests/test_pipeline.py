"""Real disposable PostgreSQL + mocked Gmail/Storage. Never touches hosted accounts."""

import asyncio
import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet

from apps.api.domain import MB, MIB
from apps.api.pipeline import (
    PrivateStorage,
    StorageLimitExceeded,
    enforce_storage_limit,
    fail_job,
    run_page,
)
from apps.api.pipeline_config import PipelineConfig
from apps.api.pipeline_security import ScannerUnavailable
from apps.api.pipeline_store import PipelineStore
from apps.api.postgres import DatabaseError, connect
from apps.api.processing import sample_pdf
from apps.api.providers import TokenCipher, Tokens


@pytest.fixture
def pipeline():
    dsn = os.getenv("CERTVAULT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip(
            "Set CERTVAULT_TEST_DATABASE_URL to the disposable migrated PostgreSQL database"
        )
    config = PipelineConfig(
        database_url=dsn,
        oauth_key=Fernet.generate_key().decode(),
        google_client_id="mock-client",
        google_client_secret="mock-secret",
        live_imports_enabled=True,
    )
    owner, other = str(uuid.uuid4()), str(uuid.uuid4())
    with connect(dsn) as db:
        db.execute("insert into auth.users(id) values(%s),(%s)", (owner, other))
        db.execute(
            "insert into public.profiles(owner_id) values(%s) on conflict(owner_id) do nothing",
            (owner,),
        )
    store = PipelineStore(dsn, owner)
    encrypted = TokenCipher(config.oauth_key.get_secret_value()).encrypt(
        owner, Tokens(access_token="mock-private-access", refresh_token="mock-private-refresh")
    )
    connection = store.connect(
        "synthetic@example.test", encrypted, datetime.now(UTC) + timedelta(hours=1), 30, False
    )
    yield config, store, connection, other
    # Only these randomized synthetic fixture users and their records are removed.
    with connect(dsn) as db:
        db.execute("delete from auth.users where id in (%s,%s)", (owner, other))


def scenario(
    config,
    store,
    connection,
    *,
    oversized=False,
    fail_scan=False,
    expired=False,
    real_security=False,
    duplicate=False,
    unknown=False,
    declared_size=None,
    storage_limit_rejected=False,
):
    pdf = sample_pdf("Pipeline security fixture", "Synthetic issuer")
    if unknown:
        pdf += b"\n" * (2 * 1048576)
    requests, stored = [], {}

    def handle(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"historyId": "anchor-100", "emailAddress": "synthetic@example.test"}
            )
        if path.endswith("/history"):
            if expired:
                return httpx.Response(404)
            return httpx.Response(200, json={"historyId": "anchor-200", "history": []})
        if path.endswith("/messages"):
            return httpx.Response(
                200,
                json={"messages": [{"id": "mail1"}, {"id": "mail2" if duplicate else "unrelated"}]},
            )
        if any(path.endswith("/messages/" + key) for key in ("mail1", "mail2", "unrelated")):
            return httpx.Response(
                200,
                json={
                    "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
                    "payload": {
                        "headers": [
                            {
                                "name": "Subject",
                                "value": "Lunch plans"
                                if path.endswith("unrelated")
                                else "Your certificate of achievement",
                            }
                        ],
                        "parts": [
                            {
                                "filename": "lunch.pdf"
                                if path.endswith("unrelated")
                                else "credential.pdf",
                                "mimeType": "application/pdf",
                                "body": {
                                    "attachmentId": "file1",
                                    "size": None
                                    if unknown
                                    else declared_size
                                    if oversized
                                    else len(pdf),
                                },
                            }
                        ],
                    },
                },
            )
        if "/attachments/" in path:
            return httpx.Response(
                200, json={"data": base64.urlsafe_b64encode(pdf).decode().rstrip("=")}
            )
        if "/storage/v1/object/" in path:
            if storage_limit_rejected:
                return httpx.Response(413, json={"message": "Payload too large"})
            stored[path] = request.content
            return httpx.Response(200, json={"Key": path})
        raise AssertionError(path)

    def scanner(data):
        assert data == pdf
        if fail_scan:
            raise ScannerUnavailable("Mocked scanner outage")

    async def run(job):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            await run_page(
                config,
                store,
                job,
                http,
                PrivateStorage(
                    http, "https://storage.example", "mock-publishable", "mock-user-jwt"
                ),
                scan_file=None if real_security else scanner,
                parse_file=None if real_security else lambda data: "Synthetic extracted text",
            )

    return run, requests, stored, pdf


def test_storage_client_rejects_oversize_before_any_request():
    class OversizedObject:
        def __len__(self):
            return 50_000_001

    with pytest.raises(StorageLimitExceeded):
        enforce_storage_limit(OversizedObject())


@pytest.mark.parametrize(
    "key",
    ["sb_secret_project_wide", "eyJ.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.signature", "s3-secret-key"],
)
def test_private_storage_rejects_project_wide_keys(key):
    with pytest.raises(ValueError, match="publishable key"):
        PrivateStorage(None, "http://127.0.0.1:54321", key, "mock-user-jwt")


def test_private_storage_uses_owner_jwt_and_publishable_key():
    storage = PrivateStorage(
        None, "http://127.0.0.1:54321", "mock-publishable-key", "mock-user-jwt"
    )
    assert storage.headers == {
        "apikey": "mock-publishable-key",
        "Authorization": "Bearer mock-user-jwt",
    }


def test_private_storage_upload_is_owner_scoped_and_never_upserts():
    owner = str(uuid.uuid4())
    pdf = sample_pdf("Synthetic certificate", "Synthetic issuer")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(201, json={"Key": request.url.path})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            storage = PrivateStorage(
                http,
                "http://127.0.0.1:54321",
                "mock-publishable",
                "owner-auth-jwt",
            )
            await storage.upload(owner, pdf)

    asyncio.run(run())
    request = requests[0]
    assert request.headers["apikey"] == "mock-publishable"
    assert request.headers["Authorization"] == "Bearer owner-auth-jwt"
    assert request.headers["x-upsert"] == "false"
    assert request.url.path.endswith(owner + "/" + hashlib.sha256(pdf).hexdigest() + ".pdf")
    assert request.content == pdf


def test_mvp_pipeline_database_configuration_rejects_every_hosted_target():
    with pytest.raises(ValueError, match="must be local loopback"):
        PipelineConfig(
            database_url="postgresql://backend:password@db.example.supabase.co:5432/postgres",
            oauth_key=Fernet.generate_key().decode(),
            google_client_id="mock-client",
            google_client_secret="mock-secret",
        )


def test_real_scanner_and_isolated_parser_in_pipeline(pipeline):
    if os.getenv("CERTVAULT_TEST_SECURITY") != "1":
        pytest.skip("Requires the local ClamAV service and built isolated parser image")
    config, store, connection, _ = pipeline
    run, _, objects, _ = scenario(config, store, connection, real_security=True)
    asyncio.run(run(store.enqueue(connection)))
    assert len(objects) == 1
    assert store.snapshot()["imports"][0]["status"] == "stored"


def test_pipeline_commits_private_certificate_notification_and_dedupes(pipeline):
    config, store, connection, other = pipeline
    run, requests, objects, pdf = scenario(config, store, connection)
    job = store.enqueue(connection)
    asyncio.run(run(job))
    snapshot = store.snapshot()
    assert snapshot["jobs"][0]["status"] == "completed"
    assert len(snapshot["imports"]) == 1  # unrelated message not retained
    assert snapshot["imports"][0]["status"] == "stored"
    assert list(objects.values()) == [pdf]
    with connect(store.dsn) as db:
        assert (
            len(
                db.execute(
                    "select * from public.certificates where owner_id=%s", (store.owner,)
                ).fetchall()
            )
            == 1
        )
    with store.db() as db:
        assert (
            len(
                db.execute(
                    "select id from public.notifications where owner_id=%s", (store.owner,)
                ).fetchall()
            )
            == 1
        )
        # RLS independently denies other owners even without a WHERE owner filter.
        db.execute("select set_config('certvault.owner',%s,true)", (other,))
        assert db.execute("select id from public.certificates").fetchall() == []
        assert db.execute("select * from private.mailbox_tokens").fetchall() == []
    asyncio.run(run(store.enqueue(connection)))
    assert len([r for r in requests if "/attachments/" in r.url.path]) == 1
    assert len(store.snapshot()["notifications"]) == 1


def test_oversized_reject_and_approve_are_specific_and_owner_scoped(pipeline):
    config, store, connection, other = pipeline
    with connect(store.dsn) as db:
        db.execute(
            "update public.profiles set download_limit_bytes=%s where owner_id=%s",
            (45 * MIB, store.owner),
        )
    run, requests, objects, _ = scenario(
        config, store, connection, oversized=True, declared_size=50 * MB
    )
    asyncio.run(run(store.enqueue(connection)))
    item = store.snapshot()["imports"][0]
    assert item["status"] == "awaiting_approval"
    assert objects == {} and not any("/attachments/" in r.url.path for r in requests)
    assert PipelineStore(store.dsn, other).decide(item["id"], True) is None
    assert store.decide(item["id"], True)
    assert store.decide(item["id"], True) is None
    asyncio.run(run(store.enqueue(connection)))
    assert store.snapshot()["imports"][0]["status"] == "stored"
    assert len(objects) == 1


@pytest.mark.parametrize("declared_size", [50 * MIB, 51 * MB, 100 * MIB])
def test_declared_files_over_storage_limit_are_never_fetched_or_uploaded(pipeline, declared_size):
    config, store, connection, _ = pipeline
    run, requests, objects, _ = scenario(
        config, store, connection, oversized=True, declared_size=declared_size
    )
    asyncio.run(run(store.enqueue(connection)))
    item = store.snapshot()["imports"][0]
    assert item["status"] == "rejected"
    assert item["safe_error"] == "storage_size_limit_exceeded"
    assert not any("/attachments/" in request.url.path for request in requests)
    assert objects == {}


def test_storage_size_rejection_is_terminal_and_user_visible(pipeline):
    config, store, connection, _ = pipeline
    run, _, objects, _ = scenario(config, store, connection, storage_limit_rejected=True)
    job = store.enqueue(connection)
    asyncio.run(run(job))
    item = store.snapshot()["imports"][0]
    assert item["status"] == "rejected"
    assert item["safe_error"] == "storage_size_limit_exceeded"
    assert "50 MB Storage limit" in store.snapshot()["notifications"][0]["safe_message"]
    assert objects == {}
    assert store.snapshot()["jobs"][0]["status"] == "completed"


def test_scanner_failure_never_uploads_and_retry_recovers(pipeline):
    config, store, connection, _ = pipeline
    run, _, objects, _ = scenario(config, store, connection, fail_scan=True)
    job = store.enqueue(connection)
    with pytest.raises(ScannerUnavailable):
        asyncio.run(run(job))
    fail_job(store, job, "scanner_unavailable")
    assert objects == {}
    assert store.snapshot()["jobs"][0]["status"] == "retry"
    recovered, _, objects, _ = scenario(config, store, connection)
    asyncio.run(recovered(job))
    assert len(objects) == 1
    assert store.snapshot()["jobs"][0]["status"] == "completed"


def test_disconnect_cancels_jobs_removes_tokens_and_stops_download(pipeline):
    config, store, connection, _ = pipeline
    job = store.enqueue(connection)
    assert store.disconnect(connection)
    run, requests, objects, _ = scenario(config, store, connection)
    asyncio.run(run(job))
    assert not requests and not objects
    assert store.snapshot()["jobs"][0]["status"] == "cancelled"
    assert store.connection(connection) is None


def test_manual_rescan_revisits_backfill_and_dedupes(pipeline):
    config, store, connection, _ = pipeline
    run, _, _, _ = scenario(config, store, connection)
    asyncio.run(run(store.enqueue(connection)))
    assert store.connection(connection)["cursor"]
    job = store.enqueue(connection, rescan=True)
    assert store.connection(connection)["cursor"] is None
    again, requests, objects, _ = scenario(config, store, connection)
    asyncio.run(again(job))
    assert not any(r.url.path.endswith("/history") for r in requests)
    assert not objects
    assert len(store.snapshot()["imports"]) == 1


def test_expired_history_backfill_is_idempotent(pipeline):
    config, store, connection, _ = pipeline
    run, _, _, _ = scenario(config, store, connection)
    asyncio.run(run(store.enqueue(connection)))
    backfill, requests, objects, _ = scenario(config, store, connection, expired=True)
    asyncio.run(backfill(store.enqueue(connection)))
    assert any(r.url.path.endswith("/history") for r in requests)
    assert not objects  # existing candidate already stored
    assert len(store.snapshot()["imports"]) == 1


def test_scheduler_and_client_roles_do_not_expose_tokens(pipeline):
    _, store, connection, _ = pipeline
    job = store.enqueue(connection)
    with connect(store.dsn) as db:
        db.execute("set local role certvault_pipeline")
        assert any(
            str(r["job_id"]) == job
            for r in db.execute("select * from private.pipeline_due()").fetchall()
        )
    with pytest.raises(DatabaseError):
        with connect(store.dsn) as db:
            db.execute("set local role authenticated")
            db.execute("select * from private.mailbox_tokens")


def test_pipeline_role_uses_only_ingestion_privileges(pipeline):
    _, store, _, _ = pipeline
    with store.db() as db:
        grants = db.execute(
            "select "
            "has_column_privilege('certvault_pipeline','public.profiles','download_limit_bytes','select') as profile_limit_read,"
            "has_column_privilege('certvault_pipeline','public.profiles','display_name','select') as profile_name_read,"
            "has_table_privilege('certvault_pipeline','public.profiles','update') as profile_update,"
            "has_column_privilege('certvault_pipeline','public.certificates','owner_id','insert') as certificate_insert,"
            "has_table_privilege('certvault_pipeline','public.certificates','update') as certificate_update,"
            "has_column_privilege('certvault_pipeline','public.audit_events','owner_id','insert') as audit_insert,"
            "has_table_privilege('certvault_pipeline','public.audit_events','select') as audit_read,"
            "has_table_privilege('certvault_pipeline','private.pipeline_items','delete') as item_delete,"
            "has_table_privilege('certvault_pipeline','private.mailbox_tokens','delete') as token_delete"
        ).fetchone()
        assert grants == {
            "profile_limit_read": True,
            "profile_name_read": False,
            "profile_update": False,
            "certificate_insert": True,
            "certificate_update": False,
            "audit_insert": True,
            "audit_read": False,
            "item_delete": False,
            "token_delete": True,
        }


def test_manual_dispatch_uses_only_ids_and_has_no_scheduler(pipeline, monkeypatch):
    from types import SimpleNamespace

    from apps.api.pipeline_routes import dispatch_manual_job
    from apps.worker.celery_app import celery, ingest_mailbox

    _, store, connection, _ = pipeline
    job = store.enqueue(connection)
    dispatched, saved = [], []

    class Sessions:
        async def setex(self, key, ttl, value):
            saved.append((key, ttl, value))

        async def delete(self, key):
            return 1

    class Cipher:
        def encrypt(self, value):
            return b"encrypted-test-session"

    monkeypatch.setattr(ingest_mailbox, "apply_async", lambda **kwargs: dispatched.append(kwargs))
    asyncio.run(
        dispatch_manual_job(
            SimpleNamespace(sessions=Sessions(), cipher=Cipher()),
            store.owner,
            job,
            "synthetic-owner-jwt",
        )
    )
    assert dispatched == [{"args": [store.owner, job], "queue": "ingestion"}]
    assert saved == [(f"cv:ingestion-session:{store.owner}:{job}", 3600, b"encrypted-test-session")]
    assert celery.conf.beat_schedule == {}


def test_page_checkpoint_and_identical_files_from_different_messages(pipeline):
    config, store, connection, _ = pipeline
    run, _, objects, _ = scenario(config, store, connection, duplicate=True)
    job = store.enqueue(connection)
    asyncio.run(run(job))
    assert store.snapshot()["jobs"][0]["status"] == "queued"
    assert store.connection(connection)["cursor"] is None
    asyncio.run(run(job))
    assert store.snapshot()["jobs"][0]["status"] == "completed"
    assert sorted(i["status"] for i in store.snapshot()["imports"]) == ["duplicate", "stored"]
    assert len(objects) == 1
    with connect(store.dsn) as db:
        assert (
            len(
                db.execute(
                    "select * from public.certificates where owner_id=%s", (store.owner,)
                ).fetchall()
            )
            == 1
        )


def test_unknown_size_stops_at_observed_bound_and_rejection_stores_nothing(pipeline):
    config, store, connection, _ = pipeline
    with connect(store.dsn) as db:
        db.execute(
            "update public.profiles set download_limit_bytes=1048576 where owner_id=%s",
            (store.owner,),
        )
    run, _, objects, _ = scenario(config, store, connection, unknown=True)
    asyncio.run(run(store.enqueue(connection)))
    item = store.snapshot()["imports"][0]
    assert item["status"] == "awaiting_approval" and not objects
    assert store.decide(item["id"], False)
    asyncio.run(run(store.enqueue(connection)))
    assert store.snapshot()["imports"][0]["status"] == "rejected" and not objects


def test_private_download_route_uses_user_token_hash_check_and_owner_scope(
    pipeline, client, monkeypatch
):
    from types import SimpleNamespace

    from pydantic import SecretStr

    from apps.api import pipeline_routes
    from apps.api.account import gateway
    from apps.api.main import app

    config, store, connection, other = pipeline
    monkeypatch.setattr(pipeline_routes, "load_pipeline", lambda: config)
    run, _, _, pdf = scenario(config, store, connection)
    asyncio.run(run(store.enqueue(connection)))
    with store.db() as db:
        certificate = db.execute(
            "select certificate_id from public.certificate_files where owner_id=%s", (store.owner,)
        ).fetchone()["certificate_id"]
    requests = []
    corrupt = False
    active_store = store

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer mock-user-jwt"
        assert "/certificates/" + store.owner + "/" in request.url.path
        return httpx.Response(200, content=pdf[:-1] + b"x" if corrupt else pdf)

    class MockGateway:
        def __init__(self, client):
            self.client = client
            self.config = SimpleNamespace(
                url="https://mock-storage.example",
                publishable_key=SecretStr("mock-publishable"),
            )

        async def identity(self, request):
            return "mock-session", active_store.owner, "mock-user-jwt"

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            yield MockGateway(http)

    app.dependency_overrides[gateway] = override
    try:
        path = f"/account/pipeline/certificates/{certificate}/download"
        response = client.get(path)
        assert response.status_code == 200 and response.content == pdf
        assert response.headers["content-disposition"] == 'attachment; filename="certificate.pdf"'
        corrupt = True
        assert client.get(path).status_code == 503
        active_store = PipelineStore(store.dsn, other)
        assert client.get(path).status_code == 404
        assert len(requests) == 2
    finally:
        app.dependency_overrides.pop(gateway, None)


def test_manual_upload_scans_stores_extracts_and_deduplicates(pipeline, client, monkeypatch):
    from types import SimpleNamespace

    from pydantic import SecretStr

    from apps.api import pipeline_config, pipeline_security
    from apps.api.account import gateway
    from apps.api.main import app
    from apps.api.processing import sample_pdf

    config, store, _, _ = pipeline
    monkeypatch.setattr(pipeline_config, "load_pipeline", lambda: config)
    scanned, stored = [], []
    pdf = sample_pdf("Certificate of Secure Python", "Example Academy")

    def record_scan(data, host, port):
        scanned.append((data, host, port))

    monkeypatch.setattr(pipeline_security, "scan", record_scan)
    monkeypatch.setattr(
        pipeline_security,
        "isolated_extract",
        lambda data, image: (
            "Course: Secure Python\nIssuer: Example Academy\nRecipient: Sample Learner"
        ),
    )

    def storage_response(request):
        stored.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-owner-jwt"
        assert request.headers["x-upsert"] == "false"
        assert request.content == pdf
        assert f"/certificates/{store.owner}/" in request.url.path
        return httpx.Response(200, json={"Key": request.url.path})

    class MockGateway:
        def __init__(self, client):
            self.client = client
            self.config = SimpleNamespace(
                url="http://127.0.0.1:54321",
                publishable_key=SecretStr("mock-publishable"),
            )

        async def identity(self, request):
            return "synthetic-session", store.owner, "synthetic-owner-jwt"

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(storage_response)) as remote:
            yield MockGateway(remote)

    app.dependency_overrides[gateway] = override
    try:

        def upload():
            return client.post(
                "/account/certificates/upload",
                files={"file": ("secure-python.pdf", pdf, "application/pdf")},
            )

        first = upload()
        assert first.status_code == 200
        assert first.json()["status"] == "stored"
        duplicate = upload()
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate"
        assert len(scanned) == 1 and len(stored) == 1
        with connect(store.dsn) as db:
            row = db.execute(
                "select c.title,c.issuer,c.source,f.bytes from public.certificates c "
                "join public.certificate_files f on f.certificate_id=c.id "
                "where c.owner_id=%s",
                (store.owner,),
            ).fetchone()
            assert row["title"] == "Secure Python"
            assert row["issuer"] == "Example Academy"
            assert row["source"] == "manual"
            assert row["bytes"] == len(pdf)
    finally:
        app.dependency_overrides.pop(gateway, None)
