"""Celery boundary. Demo worker accepts only IDs, never content/tokens in task payloads."""

import os

from celery import Celery

from apps.api.main import sync

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
