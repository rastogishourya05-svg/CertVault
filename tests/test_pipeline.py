"""Real disposable PostgreSQL + mocked Gmail/Storage. Never touches hosted accounts."""

import asyncio
import base64
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet

from apps.api.pipeline import PrivateStorage, fail_job, run_page
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
        storage_key="mock-storage-only",
        oauth_key=Fernet.generate_key().decode(),
        google_client_id="mock-client",
        google_client_secret="mock-secret",
        live_imports_enabled=True,
    )
    owner, other = str(uuid.uuid4()), str(uuid.uuid4())
    with connect(dsn) as db:
        db.execute("insert into auth.users(id) values(%s),(%s)", (owner, other))
    store = PipelineStore(dsn, owner)
    with store.db() as db:
        db.execute(
            "insert into public.profiles(owner_id) values(%s) on conflict(owner_id) do nothing",
            (owner,),
        )
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
                                "filename": "credential.pdf",
                                "mimeType": "application/pdf",
                                "body": {
                                    "attachmentId": "file1",
                                    "size": None
                                    if unknown
                                    else 51 * 1048576
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
                PrivateStorage(http, "https://storage.example", "mock-key"),
                scan_file=None if real_security else scanner,
                parse_file=None if real_security else lambda data: "Synthetic extracted text",
            )

    return run, requests, stored, pdf


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
    with store.db() as db:
        assert (
            len(
                db.execute(
                    "select * from public.certificates where owner_id=%s", (store.owner,)
                ).fetchall()
            )
            == 1
        )
        assert (
            len(
                db.execute(
                    "select * from public.notifications where owner_id=%s", (store.owner,)
                ).fetchall()
            )
            == 1
        )
        # RLS independently denies other owners even without a WHERE owner filter.
        db.execute("select set_config('certvault.owner',%s,true)", (other,))
        assert db.execute("select * from public.certificates").fetchall() == []
        assert db.execute("select * from private.mailbox_tokens").fetchall() == []
    asyncio.run(run(store.enqueue(connection)))
    assert len([r for r in requests if "/attachments/" in r.url.path]) == 1
    assert len(store.snapshot()["notifications"]) == 1


def test_oversized_reject_and_approve_are_specific_and_owner_scoped(pipeline):
    config, store, connection, other = pipeline
    run, requests, objects, _ = scenario(config, store, connection, oversized=True)
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


def test_dispatcher_uses_only_ids_and_disabled_configuration_dispatches_nothing(
    pipeline, monkeypatch
):
    from apps.api import pipeline_config
    from apps.worker.celery_app import dispatch_ingestion, ingest_mailbox

    config, store, connection, _ = pipeline
    job = store.enqueue(connection)
    dispatched = []
    monkeypatch.setattr(ingest_mailbox, "apply_async", lambda **kwargs: dispatched.append(kwargs))
    monkeypatch.setattr(pipeline_config, "load_pipeline", lambda: None)
    dispatch_ingestion.run()
    assert dispatched == []
    monkeypatch.setattr(pipeline_config, "load_pipeline", lambda: config)
    dispatch_ingestion.run()
    assert dispatched == [{"args": [store.owner, job], "queue": "ingestion"}]


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
    with store.db() as db:
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
    with store.db() as db:
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


def test_private_download_route_uses_user_token_hash_check_and_owner_scope(pipeline, client):
    from types import SimpleNamespace

    from pydantic import SecretStr

    from apps.api.main import app
    from apps.api.pipeline_routes import context

    config, store, connection, other = pipeline
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

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            yield (
                config,
                active_store,
                SimpleNamespace(
                    client=http,
                    config=SimpleNamespace(
                        url="https://mock-storage.example",
                        publishable_key=SecretStr("mock-publishable"),
                    ),
                ),
                "mock-user-jwt",
                "mock-session",
            )

    app.dependency_overrides[context] = override
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
        app.dependency_overrides.pop(context, None)
