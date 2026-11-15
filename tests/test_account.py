import json
from contextlib import asynccontextmanager

import httpx
import pytest
from cryptography.fernet import Fernet
from redis.exceptions import RedisError

from apps.api.account import AccountConfig, Gateway, gateway
from apps.api.main import app

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class MemorySessions:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value

    async def delete(self, key):
        self.values.pop(key, None)

    async def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key, ttl):
        pass

    @asynccontextmanager
    async def lock(self, *args, **kwargs):
        yield


@pytest.fixture
def account(client):
    sessions = MemorySessions()
    requests = []
    state = {
        "expired": False,
        "invalid_login": False,
        "profile": [],
        "certs": [],
        "reject_patch": False,
    }
    settings = AccountConfig(
        url="https://abcdefghijklmnopqrst.supabase.co",
        publishable_key="publishable-test",
        session_key=Fernet.generate_key().decode(),
        enabled=True,
    )

    def handle(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/token"):
            if state["invalid_login"]:
                return httpx.Response(400, json={"msg": "private provider diagnostics"})
            return httpx.Response(
                200,
                json={
                    "access_token": "private-access-token",
                    "refresh_token": "private-refresh-token",
                    "expires_in": 3600,
                },
            )
        if path.endswith("/user"):
            return (
                httpx.Response(401, json={"msg": "revoked"})
                if state["expired"]
                else httpx.Response(200, json={"id": OWNER})
            )
        if path.endswith("/logout"):
            return httpx.Response(204)
        if path.endswith("/profiles"):
            if request.method == "GET":
                return httpx.Response(200, json=state["profile"])
            body = json.loads(request.content)
            assert request.url.params.get("owner_id", f"eq.{OWNER}") == f"eq.{OWNER}"
            if request.method == "POST":
                assert body["owner_id"] == OWNER
            state["profile"] = [
                {
                    "display_name": body["display_name"],
                    "download_limit_bytes": body["download_limit_bytes"],
                }
            ]
            return httpx.Response(201, json=state["profile"])
        if path.endswith("/certificates"):
            assert request.url.params["owner_id"] == f"eq.{OWNER}"
            if request.method == "PATCH":
                return httpx.Response(200, json=[] if state["reject_patch"] else [{}])
            return httpx.Response(200, json=state["certs"])
        raise AssertionError(path)

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            yield Gateway(settings, http, sessions)

    app.dependency_overrides[gateway] = override
    yield client, sessions, requests, state, settings
    app.dependency_overrides.pop(gateway, None)


def sign_in(client):
    return client.post(
        "/account/login", json={"email": "learner@example.test", "password": "a-test-password"}
    )


def test_opaque_cookie_and_encrypted_server_tokens(account):
    client, sessions, requests, _, _ = account
    result = sign_in(client)
    assert result.status_code == 200
    assert (
        "HttpOnly" in result.headers["set-cookie"]
        and "SameSite=strict" in result.headers["set-cookie"]
    )
    assert "private-access" not in result.text and "private-refresh" not in result.text
    session = next(v for k, v in sessions.values.items() if k.startswith("cv:session:"))
    assert b"private-access" not in session
    assert client.get("/account/status").json()["authenticated"]
    assert requests[-1].headers["Authorization"] == "Bearer private-access-token"


def test_session_refresh_and_revocation(account):
    client, sessions, requests, state, settings = account
    sign_in(client)
    key = next(k for k in sessions.values if k.startswith("cv:session:"))
    cipher = Fernet(settings.session_key.get_secret_value().encode())
    saved = json.loads(cipher.decrypt(sessions.values[key]))
    saved["expires_at"] = 0
    sessions.values[key] = cipher.encrypt(json.dumps(saved).encode())
    assert client.get("/account/status").json()["authenticated"]
    assert any(r.url.params.get("grant_type") == "refresh_token" for r in requests)
    state["expired"] = True
    assert not client.get("/account/status").json()["authenticated"]
    assert key not in sessions.values
    assert client.get("/account/certificates").status_code == 401


def test_profile_and_search_use_authenticated_owner(account):
    client, _, requests, state, _ = account
    sign_in(client)
    assert client.get("/account/profile").json()["display_name"] == "Your workspace"
    body = {"display_name": "My real workspace", "download_limit_bytes": 1048576}
    assert client.put("/account/profile", json=body).status_code == 200
    assert client.get("/account/profile").json() == body
    assert client.get("/account/certificates?q=cloud").status_code == 200
    assert requests[-1].url.params["search_document"] == "wfts(simple).cloud"
    state["reject_patch"] = True
    assert (
        client.patch(
            f"/account/certificates/{OTHER}",
            json={"title": "New", "issuer": "Issuer", "favorite": True},
        ).status_code
        == 404
    )
    assert client.put("/account/profile", json={**body, "owner_id": OTHER}).status_code == 422


def test_sign_out_revokes_local_provider_session(account):
    client, sessions, requests, _, _ = account
    sign_in(client)
    result = client.post("/account/logout")
    assert result.json()["provider_revocation_confirmed"]
    assert requests[-1].url.params["scope"] == "local"
    assert not any(k.startswith("cv:session:") for k in sessions.values)
    assert client.get("/account/status").json()["authenticated"] is False


def test_safe_errors_and_rate_limit(account):
    client, _, _, state, _ = account
    state["invalid_login"] = True
    for _ in range(5):
        result = sign_in(client)
        assert result.status_code == 401 and "private provider" not in result.text
    assert sign_in(client).status_code == 429


def test_logout_clears_cookie_even_when_session_store_fails(account, monkeypatch):
    client, sessions, _, _, _ = account
    sign_in(client)

    async def fail(*args):
        raise RedisError("private connection details")

    monkeypatch.setattr(sessions, "get", fail)
    monkeypatch.setattr(sessions, "delete", fail)
    result = client.post("/account/logout")
    assert result.status_code == 200
    assert not result.json()["provider_revocation_confirmed"]
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert "private connection" not in result.text


def test_unconfigured_account_is_explicit(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CERTVAULT_ACCOUNT_CONFIG", str(tmp_path / "absent.json"))
    assert client.get("/account/config").json()["configured"] is False
    assert (
        client.post(
            "/account/login", json={"email": "learner@example.test", "password": "test"}
        ).status_code
        == 503
    )
