"""Real Redis/Celery smoke test; uses only a fresh synthetic local workspace."""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.worker.celery_app import sync_demo_mailbox


def main():
    with tempfile.TemporaryDirectory(prefix="worker-check-", dir=".local") as folder:
        os.environ["CERTVAULT_DATA_DIR"] = str(Path(folder).resolve())
        os.environ["CERTVAULT_MODE"] = "demo"
        with TestClient(app) as client:
            owner = client.post("/auth/demo").json()["id"]
            client.post("/connections", json={"provider": "gmail", "consent": True})
            connection = client.get("/connections").json()[0]["id"]
            with open(".local/worker-check.log", "w") as log:
                queue = "certvault-smoke-" + uuid.uuid4().hex
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "celery",
                        "-A",
                        "apps.worker.celery_app:celery",
                        "worker",
                        "--pool=solo",
                        "--loglevel=WARNING",
                        "--without-gossip",
                        "--without-mingle",
                        "--without-heartbeat",
                        "--queues=" + queue,
                    ],
                    stdout=log,
                    stderr=log,
                    env=os.environ.copy(),
                )
                try:
                    sync_demo_mailbox.apply_async(args=[owner, connection], queue=queue)
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        if len(client.get("/certificates").json()) == 3:
                            break
                        time.sleep(0.5)
                    else:
                        raise RuntimeError(
                            "Worker did not complete sample import; inspect .local/worker-check.log"
                        )
                    assert len(client.get("/imports").json()) == 4
                    assert len(client.get("/notifications").json()) == 4
                    print(
                        "Real Redis/Celery task: 3 stored certificates, 1 approval, 4 notifications; passed"
                    )
                finally:
                    worker.terminate()
                    worker.wait(timeout=10)


if __name__ == "__main__":
    main()
