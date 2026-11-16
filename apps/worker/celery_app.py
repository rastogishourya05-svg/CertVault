"""Celery boundary. Demo worker accepts only IDs, never content/tokens in task payloads."""

import asyncio
import os

import httpx
from celery import Celery
from cryptography.fernet import Fernet, InvalidToken
from redis import Redis

from apps.api.main import sync
from apps.api.postgres import DatabaseError

celery = Celery("certvault", broker=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=90,
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
)


@celery.task(
    bind=True,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
    rate_limit="6/m",
    ignore_result=True,
)
def sync_demo_mailbox(self, owner_id: str, connection_id: str):
    if os.getenv("CERTVAULT_MODE", "demo") != "demo":
        raise RuntimeError("Live providers not enabled")
    return sync(connection_id, owner_id)


@celery.task(
    name="certvault.ingest_mailbox",
    ignore_result=True,
    rate_limit="12/m",
    soft_time_limit=240,
    time_limit=270,
)
def ingest_mailbox(owner_id: str, job_id: str):
    from apps.api.account import config as account_config
    from apps.api.pipeline import PrivateStorage, fail_job, run_page
    from apps.api.pipeline_config import load_pipeline
    from apps.api.pipeline_security import ScannerUnavailable
    from apps.api.pipeline_store import PipelineStore
    from apps.api.providers import ProviderUnavailable, RetryableProviderError

    config, account = load_pipeline(), account_config()
    if not config or not account or not config.live_imports_enabled:
        return
    store = PipelineStore(config.database_url.get_secret_value(), owner_id)
    redis_client = Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    token_key = f"cv:ingestion-session:{owner_id}:{job_id}"
    ciphertext = redis_client.get(token_key)
    if not ciphertext:
        fail_job(store, job_id, "owner_session_expired", retry=False)
        redis_client.close()
        return
    try:
        access_token = (
            Fernet(account.session_key.get_secret_value().encode()).decrypt(ciphertext).decode()
        )
    except (InvalidToken, UnicodeDecodeError, ValueError):
        fail_job(store, job_id, "owner_session_expired", retry=False)
        redis_client.delete(token_key)
        redis_client.close()
        return
    keep_token = False

    async def run():
        async with httpx.AsyncClient() as http:
            storage = PrivateStorage(
                http, account.url, account.publishable_key.get_secret_value(), access_token
            )
            await run_page(config, store, job_id, http, storage)

    try:
        asyncio.run(run())
        status = store.job_status(job_id)
        if status == "queued":
            # Continue the owner-requested backfill page by page. No job exists
            # until the owner explicitly clicks Scan now.
            ingest_mailbox.apply_async(args=[owner_id, job_id], queue="ingestion")
            keep_token = True
        elif status == "retry":
            ingest_mailbox.apply_async(args=[owner_id, job_id], queue="ingestion", countdown=30)
            keep_token = True
    except (RetryableProviderError, ScannerUnavailable, OSError, httpx.RequestError):
        fail_job(store, job_id, "temporary_dependency_failure")
    except ProviderUnavailable:
        fail_job(store, job_id, "mailbox_reconnect_or_review_required", retry=False)
    except (ValueError, DatabaseError):
        fail_job(store, job_id, "pipeline_processing_failed", retry=False)
    finally:
        if not keep_token and store.job_status(job_id) == "retry":
            # Retry the existing user-requested job, not a new mailbox scan.
            # Keep its short-lived owner session until the bounded retry completes.
            ingest_mailbox.apply_async(args=[owner_id, job_id], queue="ingestion", countdown=30)
            keep_token = True
        # User JWTs are never task arguments or logs. Keep only a short-lived
        # credential for a page continuation; Redis TTL handles worker crashes.
        if not keep_token:
            redis_client.delete(token_key)
        redis_client.close()
