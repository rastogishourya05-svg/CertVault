import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CERTVAULT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CERTVAULT_MODE", "demo")
    with TestClient(app) as c:
        c.post("/auth/demo")
        yield c


@pytest.fixture
def imported(client):
    client.post("/connections", json={"provider": "gmail", "consent": True})
    connection = client.get("/connections").json()[0]
    assert client.post(f"/connections/{connection['id']}/sync").status_code == 200
    return client, connection
