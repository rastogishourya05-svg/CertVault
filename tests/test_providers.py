import asyncio
import base64
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from apps.api.domain import PolicyError
from apps.api.providers import (
    GmailAdapter,
    GraphAdapter,
    OAuthConfig,
    ProviderUnavailable,
    RetryableProviderError,
    TokenCipher,
    Tokens,
    begin_authorization,
    consume_state,
    exchange_code,
    refresh_access,
)
from apps.api.store import db


def config(provider="gmail"):
    return OAuthConfig(
        provider, "test-client", SecretStr("test-secret"), "https://app.example/oauth/callback"
    )


def test_state_pkce_binding_expiry_and_replay(client):
    cipher = TokenCipher(Fernet.generate_key().decode())
    url = begin_authorization(config(), "user-a", cipher)
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    with pytest.raises(ProviderUnavailable):
        consume_state(state, "user-b", "gmail", cipher)
    verifier = consume_state(state, "user-a", "gmail", cipher)
    assert len(verifier) >= 43
    with pytest.raises(ProviderUnavailable):
        consume_state(state, "user-a", "gmail", cipher)
    query = parse_qs(urlsplit(begin_authorization(config(), "user-a", cipher)).query)
    with db() as c:
        c.execute("UPDATE oauth_states SET expires=?", (time.time() - 1,))
    with pytest.raises(ProviderUnavailable):
        consume_state(query["state"][0], "user-a", "gmail", cipher)


def test_tokens_encrypted_and_owner_bound():
    cipher = TokenCipher(Fernet.generate_key().decode())
    tokens = Tokens(access_token="private-access-value", refresh_token="private-refresh-value")
    encoded = cipher.encrypt("user-a", tokens)
    assert b"private-access-value" not in encoded
    assert "private-access-value" not in repr(tokens)
    assert (
        cipher.decrypt("user-a", encoded).access_token.get_secret_value() == "private-access-value"
    )
    with pytest.raises(ProviderUnavailable):
        cipher.decrypt("user-b", encoded)


def test_code_exchange_and_refresh_preserves_rotating_tokens():
    async def scenario():
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            tokens = await exchange_code(http, config(), "code", "verifier")
            assert tokens.access_token.get_secret_value() == "new-access"
            current = Tokens(access_token="old", refresh_token="refresh")
            updated = await refresh_access(http, config(), current)
            assert updated.refresh_token.get_secret_value() == "refresh"
        assert b"code_verifier=verifier" in requests[0].content
        assert b"grant_type=refresh_token" in requests[1].content

    asyncio.run(scenario())


def test_gmail_pagination_and_bounded_decoded_attachment():
    async def scenario():
        def handle(request):
            if "/attachments/" in request.url.path:
                return httpx.Response(
                    200, json={"data": base64.urlsafe_b64encode(b"123456789").decode().rstrip("=")}
                )
            assert request.url.params["pageToken"] == "next-page"
            return httpx.Response(
                200, json={"messages": [{"id": "mail1"}], "nextPageToken": "last-page"}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            adapter = GmailAdapter(http, SecretStr("secret"))
            result = await adapter.messages("next-page")
            assert result["nextPageToken"] == "last-page"
            with pytest.raises(PolicyError):
                await adapter.attachment("mail1", "file1", 8)
            assert await adapter.attachment("mail1", "file1", 9) == b"123456789"

    asyncio.run(scenario())


def test_graph_cursor_cannot_exfiltrate_bearer_token():
    async def scenario():
        called = []

        def handle(request):
            called.append(request)
            return httpx.Response(200, json={"value": [], "@odata.deltaLink": "next"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            adapter = GraphAdapter(http, SecretStr("secret"))
            for url in [
                "https://evil.example/v1.0/me/mailFolders/inbox/messages/delta",
                "https://graph.microsoft.com@evil.example/v1.0/me/mailFolders/inbox/messages/delta",
                "http://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta",
            ]:
                with pytest.raises(ProviderUnavailable):
                    await adapter.delta(url)
            assert not called
            assert await adapter.delta() == {"value": [], "@odata.deltaLink": "next"}

    asyncio.run(scenario())


def test_throttle_safe_errors_and_no_redirect_following():
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, json={"error": "sensitive provider payload"})
            )
        ) as http:
            with pytest.raises(RetryableProviderError) as caught:
                await GmailAdapter(http, SecretStr("secret")).messages()
            assert "sensitive" not in str(caught.value)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(302, headers={"Location": "https://evil.example"})
            )
        ) as http:
            with pytest.raises(ProviderUnavailable):
                await GmailAdapter(http, SecretStr("secret")).messages()

    asyncio.run(scenario())
