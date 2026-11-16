"""Credential-gated provider adapters. Not wired into the demo HTTP API.

No provider call is made at import/startup. Tests use httpx.MockTransport.
Tokens stay server-side; callers must persist encrypted values and enforce consent.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet
from pydantic import BaseModel, SecretStr

from apps.api.domain import (
    STORAGE_HARD_CAP as HARD_CAP,
)
from apps.api.domain import (
    HardLimitExceeded,
    PolicyError,
    bounded_bytes,
)
from apps.api.store import db


class ProviderUnavailable(RuntimeError):
    """A safe error; never include a raw provider response containing tokens/content."""


class RetryableProviderError(ProviderUnavailable):
    pass


class ProviderNotFound(ProviderUnavailable):
    pass


class Tokens(BaseModel):
    access_token: SecretStr
    refresh_token: SecretStr | None = None
    expires_in: int = 3600
    token_type: str = "Bearer"


class TokenCipher:
    def __init__(self, key: str):
        self.cipher = Fernet(key.encode())

    def encrypt(self, owner_id: str, tokens: Tokens) -> bytes:
        payload = {
            "owner": owner_id,
            "access_token": tokens.access_token.get_secret_value(),
            "refresh_token": tokens.refresh_token.get_secret_value()
            if tokens.refresh_token
            else None,
            "expires_in": tokens.expires_in,
            "token_type": tokens.token_type,
        }
        return self.cipher.encrypt(json.dumps(payload).encode())

    def decrypt(self, owner_id: str, ciphertext: bytes) -> Tokens:
        payload = json.loads(self.cipher.decrypt(ciphertext))
        if not secrets.compare_digest(payload.pop("owner"), owner_id):
            raise ProviderUnavailable("Token owner mismatch")
        return Tokens(**payload)


@dataclass(frozen=True)
class OAuthConfig:
    provider: Literal["gmail", "outlook"]
    client_id: str
    client_secret: SecretStr
    redirect_uri: str

    @property
    def authorize_endpoint(self):
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            if self.provider == "gmail"
            else "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        )

    @property
    def token_endpoint(self):
        return (
            "https://oauth2.googleapis.com/token"
            if self.provider == "gmail"
            else "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        )

    @property
    def scope(self):
        return (
            "https://www.googleapis.com/auth/gmail.readonly"
            if self.provider == "gmail"
            else "offline_access https://graph.microsoft.com/Mail.Read"
        )


def begin_authorization(config: OAuthConfig, owner_id: str, cipher: TokenCipher) -> str:
    if not config.client_id or not config.client_secret.get_secret_value():
        raise ProviderUnavailable("Mailbox OAuth credentials are not configured")
    if urlsplit(config.redirect_uri).scheme != "https":
        raise ProviderUnavailable("Production OAuth callback requires HTTPS")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    with db() as c:
        c.execute("DELETE FROM oauth_states WHERE expires<?", (time.time(),))
        c.execute(
            "INSERT INTO oauth_states VALUES (?,?,?,?,?)",
            (
                hashlib.sha256(state.encode()).hexdigest(),
                owner_id,
                config.provider,
                cipher.cipher.encrypt(verifier.encode()),
                time.time() + 600,
            ),
        )
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": config.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if config.provider == "gmail":
        params.update(access_type="offline", prompt="consent", include_granted_scopes="true")
    return config.authorize_endpoint + "?" + urlencode(params)


def consume_state(state: str, owner_id: str, provider: str, cipher: TokenCipher) -> str:
    hashed = hashlib.sha256(state.encode()).hexdigest()
    with db() as c:
        item = c.execute(
            "SELECT * FROM oauth_states WHERE hash=? AND owner=? AND provider=? AND expires>?",
            (hashed, owner_id, provider, time.time()),
        ).fetchone()
        if not item:
            raise ProviderUnavailable(
                "OAuth state expired, already used, or does not match this session"
            )
        c.execute("DELETE FROM oauth_states WHERE hash=?", (hashed,))
    return cipher.cipher.decrypt(item["verifier"]).decode()


async def safe_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> dict:
    try:
        async with client.stream(
            method, url, follow_redirects=False, timeout=20, **kwargs
        ) as response:
            if response.status_code in (429, 500, 502, 503, 504):
                raise RetryableProviderError(
                    "Mailbox provider throttled or temporarily unavailable"
                )
            if response.status_code == 404:
                raise ProviderNotFound("Provider resource no longer available")
            if not 200 <= response.status_code < 300:
                raise ProviderUnavailable(
                    "Mailbox authorization or request failed; reconnect if needed"
                )
            chunks, observed = [], 0
            async for chunk in response.aiter_bytes(65536):
                observed += len(chunk)
                if observed > 8 * 1024 * 1024:
                    raise ProviderUnavailable("Mailbox metadata response exceeded limit")
                chunks.append(chunk)
    except httpx.RequestError as exc:
        raise RetryableProviderError("Mailbox provider temporarily unavailable") from exc
    try:
        payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("Expected object")
        return payload
    except (ValueError, TypeError) as exc:
        raise ProviderUnavailable("Invalid mailbox provider response") from exc


async def exchange_code(
    client: httpx.AsyncClient, config: OAuthConfig, code: str, verifier: str
) -> Tokens:
    result = await safe_json(
        client,
        "POST",
        config.token_endpoint,
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret.get_secret_value(),
            "redirect_uri": config.redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
        },
    )
    return Tokens.model_validate(result)


async def refresh_access(client: httpx.AsyncClient, config: OAuthConfig, current: Tokens) -> Tokens:
    if not current.refresh_token:
        raise ProviderUnavailable("Mailbox authorization expired; reconnect this account")
    result = await safe_json(
        client,
        "POST",
        config.token_endpoint,
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret.get_secret_value(),
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token.get_secret_value(),
        },
    )
    refreshed = Tokens.model_validate(result)
    if not refreshed.refresh_token:
        refreshed.refresh_token = current.refresh_token
    return refreshed


class GmailAdapter:
    root = "https://gmail.googleapis.com/gmail/v1/users/me/"

    def __init__(self, client: httpx.AsyncClient, token: SecretStr):
        self.client, self.headers = client, {"Authorization": f"Bearer {token.get_secret_value()}"}

    async def messages(self, page_token: str | None = None, days: int = 90) -> dict:
        params = {
            "q": f"newer_than:{days}d has:attachment filename:pdf",
            "maxResults": 10,
        }
        if page_token:
            params["pageToken"] = page_token
        return await safe_json(
            self.client, "GET", self.root + "messages", params=params, headers=self.headers
        )

    async def profile(self) -> dict:
        return await safe_json(self.client, "GET", self.root + "profile", headers=self.headers)

    async def message(self, message_id: str) -> dict:
        return await safe_json(
            self.client,
            "GET",
            self.root + f"messages/{_id(message_id)}",
            params={"format": "full"},
            headers=self.headers,
        )

    async def history(self, cursor: str, page_token: str | None = None) -> dict:
        params = {"startHistoryId": cursor, "historyTypes": "messageAdded", "maxResults": 10}
        if page_token:
            params["pageToken"] = page_token
        return await safe_json(
            self.client, "GET", self.root + "history", params=params, headers=self.headers
        )

    async def attachment(
        self, message_id: str, attachment_id: str, limit: int, approved=False
    ) -> bytes:
        url = self.root + f"messages/{_id(message_id)}/attachments/{_id(attachment_id)}"
        # Base64 JSON must be bounded before parsing or decoding. Never trust declared size.
        max_decoded = HARD_CAP if approved else min(limit, HARD_CAP)
        max_encoded = ((max_decoded + 2) // 3) * 4 + 4096
        async with self.client.stream(
            "GET", url, headers=self.headers, timeout=30, follow_redirects=False
        ) as response:
            if response.status_code in (429, 500, 502, 503, 504):
                raise RetryableProviderError("Attachment provider temporarily unavailable")
            if response.status_code != 200:
                raise ProviderUnavailable("Unable to retrieve attachment")
            parts, observed = [], 0
            async for chunk in response.aiter_bytes(65536):
                observed += len(chunk)
                if observed > max_encoded:
                    if max_decoded == HARD_CAP:
                        raise HardLimitExceeded(
                            "File exceeds the 50 MB (50,000,000-byte) storage limit"
                        )
                    raise PolicyError("Encoded attachment exceeds download limit")
                parts.append(chunk)
        try:
            encoded = json.loads(b"".join(parts))["data"]
            data = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderUnavailable("Invalid attachment encoding") from exc
        return bounded_bytes([data], limit, approved, hard_cap=HARD_CAP)


def _id(value: str) -> str:
    if (
        not value
        or len(value) > 1024
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-="
            for c in value
        )
    ):
        raise ProviderUnavailable("Invalid provider identifier")
    return value


class GraphAdapter:
    root = "https://graph.microsoft.com/v1.0/"

    def __init__(self, client: httpx.AsyncClient, token: SecretStr):
        self.client, self.headers = client, {"Authorization": f"Bearer {token.get_secret_value()}"}

    async def delta(self, cursor_url: str | None = None) -> dict:
        url = (
            cursor_url
            or self.root
            + "me/mailFolders/inbox/messages/delta?$select=id,subject,hasAttachments,receivedDateTime&$top=50"
        )
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/me/mailFolders/")
            or not parsed.path.endswith("/messages/delta")
        ):
            raise ProviderUnavailable("Invalid Graph cursor URL")
        return await safe_json(self.client, "GET", url, headers=self.headers)

    async def attachments(self, message_id: str) -> dict:
        return await safe_json(
            self.client,
            "GET",
            self.root + f"me/messages/{_id(message_id)}/attachments",
            params={"$select": "id,name,contentType,size,isInline"},
            headers=self.headers,
        )

    async def attachment(
        self, message_id: str, attachment_id: str, limit: int, approved=False
    ) -> bytes:
        url = self.root + f"me/messages/{_id(message_id)}/attachments/{_id(attachment_id)}/$value"
        chunks, count = [], 0
        cap = HARD_CAP if approved else min(limit, HARD_CAP)
        async with self.client.stream(
            "GET", url, headers=self.headers, timeout=30, follow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise ProviderUnavailable("Unable to retrieve attachment")
            async for chunk in response.aiter_bytes(65536):
                count += len(chunk)
                if count > cap:
                    if cap == HARD_CAP:
                        raise HardLimitExceeded(
                            "File exceeds the 50 MB (50,000,000-byte) storage limit"
                        )
                    raise PolicyError("Observed attachment exceeds download limit")
                chunks.append(chunk)
        return bounded_bytes(chunks, limit, approved, hard_cap=HARD_CAP)
