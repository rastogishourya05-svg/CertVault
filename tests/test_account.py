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

    async def getdel(self, key):
        return self.values.pop(key, None)

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
        "signup_confirmation": False,
        "profile": [],
        "certs": [],
        "reject_patch": False,
        "rest_error": None,
    }
    settings = AccountConfig(
        url="http://127.0.0.1:54321",
        publishable_key="publishable-test",
        session_key=Fernet.generate_key().decode(),
        enabled=True,
    )

    def handle(request):
        requests.append(request)
        path = request.url.path
        if path.startswith("/rest/") and state["rest_error"]:
            return httpx.Response(
                state["rest_error"], json={"message": "private database diagnostic"}
            )
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
        if path.endswith("/signup"):
            if state["signup_confirmation"]:
                return httpx.Response(200, json={"user": {"id": OWNER}})
            return httpx.Response(
                200,
                json={
                    "access_token": "private-access-token",
                    "refresh_token": "private-refresh-token",
                    "expires_in": 3600,
                    "user": {"id": OWNER},
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


def test_pipeline_is_disabled_and_never_authorizes_without_configuration(account, monkeypatch):
    from apps.api import pipeline_routes

    client, _, requests, _, _ = account
    monkeypatch.setattr(pipeline_routes, "load_pipeline", lambda: None)
    sign_in(client)
    assert client.get("/account/pipeline/status").json()["enabled"] is False
    result = client.post("/account/pipeline/gmail/authorize", json={"consent": True})
    assert result.status_code == 503
    assert all("google" not in str(r.url) for r in requests)


def test_account_config_allows_only_supabase_https_or_local_loopback():
    common = {
        "publishable_key": "test-key",
        "session_key": Fernet.generate_key().decode(),
        "enabled": True,
    }
    assert AccountConfig(url="http://127.0.0.1:54321", **common)
    with pytest.raises(ValueError):
        AccountConfig(url="http://192.168.1.5:54321", **common)
    with pytest.raises(ValueError):
        AccountConfig(url="http://localhost:54321", **common)


def test_pipeline_oauth_pkce_session_binding_and_single_use(account, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from apps.api import pipeline_routes
    from apps.api.pipeline_config import PipelineConfig
    from apps.api.providers import Tokens

    client, sessions, _, _, _ = account
    config = PipelineConfig(
        database_url="postgresql://postgres@127.0.0.1:54322/postgres",
        oauth_key=Fernet.generate_key().decode(),
        google_client_id="mock-client",
        google_client_secret="mock-secret",
        live_imports_enabled=True,
    )
    monkeypatch.setattr(pipeline_routes, "load_pipeline", lambda: config)
    connected = []

    class Store:
        def __init__(self, dsn, owner):
            self.owner = owner

        def connect(self, *args):
            connected.append(args)

    async def exchange(*args):
        return Tokens(access_token="mail-access", refresh_token="mail-refresh")

    async def profile(*args):
        return {"emailAddress": "synthetic@example.test"}

    monkeypatch.setattr(pipeline_routes, "PipelineStore", Store)
    monkeypatch.setattr(pipeline_routes, "exchange_code", exchange)
    monkeypatch.setattr(pipeline_routes.GmailAdapter, "profile", profile)
    sign_in(client)
    denied = client.post("/account/pipeline/gmail/authorize", json={"consent": False})
    assert denied.status_code == 422
    result = client.post(
        "/account/pipeline/gmail/authorize", json={"consent": True, "scan_days": 7}
    )
    params = parse_qs(urlsplit(result.json()["url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [config.redirect_uri]
    state = params["state"][0]
    assert b"mock-secret" not in next(
        v for k, v in sessions.values.items() if k.startswith("cv:oauth:")
    )
    path = "/account/pipeline/gmail/callback?state=" + state + "&code=synthetic-code"
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith(
        "mailbox=connected"
    )
    assert len(connected) == 1 and b"mail-access" not in connected[0][1]
    assert client.get(path, follow_redirects=False).headers["location"].endswith("mailbox=failed")
    assert len(connected) == 1


def test_pipeline_oauth_requires_callback_binding(account, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from apps.api import pipeline_routes
    from apps.api.pipeline_config import PipelineConfig

    client, _, requests, _, _ = account
    config = PipelineConfig(
        database_url="postgresql://postgres@127.0.0.1:54322/postgres",
        oauth_key=Fernet.generate_key().decode(),
        google_client_id="mock-client",
        google_client_secret="mock-secret",
        live_imports_enabled=True,
    )
    monkeypatch.setattr(pipeline_routes, "load_pipeline", lambda: config)
    sign_in(client)
    result = client.post("/account/pipeline/gmail/authorize", json={"consent": True})
    state = parse_qs(urlsplit(result.json()["url"]).query)["state"][0]
    client.cookies.delete("cv_mail_oauth")
    response = client.get(
        "/account/pipeline/gmail/callback",
        params={"state": state, "code": "synthetic"},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("mailbox=failed")
    assert all("google" not in str(r.url) for r in requests)


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


def test_local_registration_creates_opaque_server_session(account):
    client, _, _, _, _ = account
    result = client.post(
        "/account/register",
        json={"email": "new-learner@example.test", "password": "a-test-password"},
    )
    assert result.status_code == 201
    assert result.json()["authenticated"] is True
    assert "HttpOnly" in result.headers["set-cookie"]
    assert client.get("/account/status").json()["authenticated"]


def test_local_registration_reports_confirmation_without_exposing_provider_data(account):
    client, _, _, state, _ = account
    state["signup_confirmation"] = True
    result = client.post(
        "/account/register",
        json={"email": "new-learner@example.test", "password": "a-test-password"},
    )
    assert result.status_code == 201
    assert result.json() == {"authenticated": False, "confirmation_required": True}


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


def test_favorite_does_not_resubmit_or_overwrite_metadata(account):
    client, _, requests, state, _ = account
    sign_in(client)
    result = client.put(f"/account/certificates/{OWNER}/favorite", json={"value": True})
    assert result.status_code == 200
    assert json.loads(requests[-1].content) == {"favorite": True}
    assert requests[-1].url.params["owner_id"] == f"eq.{OWNER}"
    state["reject_patch"] = True
    assert (
        client.put(f"/account/certificates/{OTHER}/favorite", json={"value": True}).status_code
        == 404
    )
    assert (
        client.put(
            f"/account/certificates/{OWNER}/favorite", json={"value": True, "title": "stale title"}
        ).status_code
        == 422
    )


def test_data_validation_error_is_not_misreported_as_bad_login(account):
    client, sessions, _, state, _ = account
    sign_in(client)
    state["rest_error"] = 422
    result = client.get("/account/profile")
    assert result.status_code == 422
    assert "private database" not in result.text
    assert any(k.startswith("cv:session:") for k in sessions.values)


def test_revoked_session_cleanup_failure_does_not_leak_store_errors(account, monkeypatch):
    client, sessions, _, state, _ = account
    sign_in(client)
    state["expired"] = True

    async def fail(*args):
        raise RedisError("private cleanup details")

    monkeypatch.setattr(sessions, "delete", fail)
    result = client.get("/account/status")
    assert result.status_code == 200
    assert not result.json()["authenticated"]
    assert "private cleanup" not in result.text


def test_clear_notifications_is_owner_scoped_and_preserves_data(client):
    calls = []

    class NotificationsGateway:
        async def identity(self, request):
            return "session", OWNER, "private-token"

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            return []

    app.dependency_overrides[gateway] = lambda: NotificationsGateway()
    try:
        assert client.post("/account/notifications/read").status_code == 200
        method, path, kwargs = calls[0]
        assert method == "PATCH" and path == "/rest/v1/notifications"
        assert kwargs["params"] == {"owner_id": "eq." + OWNER, "read_at": "is.null"}
        assert list(kwargs["body"]) == ["read_at"]
    finally:
        app.dependency_overrides.pop(gateway, None)
