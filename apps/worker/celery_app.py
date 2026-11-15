"""Celery boundary. Demo worker accepts only IDs, never content/tokens in task payloads."""

import asyncio
import os

import httpx
from celery import Celery

from apps.api.main import sync
from apps.api.postgres import DatabaseError, connect

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
    beat_schedule={
        "dispatch-ingestion": {"task": "certvault.dispatch_ingestion", "schedule": 30.0}
    },
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


@celery.task(name="certvault.dispatch_ingestion", ignore_result=True)
def dispatch_ingestion():
    from apps.api.pipeline_config import load_pipeline

    config = load_pipeline()
    if not config or not config.live_imports_enabled:
        return
    with connect(config.database_url.get_secret_value()) as db:
        db.execute("set local role certvault_pipeline")
        rows = db.execute("select * from private.pipeline_due()").fetchall()
    for row in rows:
        job, owner = row["job_id"], row["owner_id"]
        ingest_mailbox.apply_async(args=[str(owner), str(job)], queue="ingestion")


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

    async def run():
        async with httpx.AsyncClient() as http:
            storage = PrivateStorage(http, account.url, config.storage_key.get_secret_value())
            await run_page(config, store, job_id, http, storage)

    try:
        asyncio.run(run())
    except (RetryableProviderError, ScannerUnavailable, OSError, httpx.RequestError):
        fail_job(store, job_id, "temporary_dependency_failure")
    except ProviderUnavailable:
        fail_job(store, job_id, "mailbox_reconnect_or_review_required", retry=False)
    except (ValueError, DatabaseError):
        fail_job(store, job_id, "pipeline_processing_failed", retry=False)
