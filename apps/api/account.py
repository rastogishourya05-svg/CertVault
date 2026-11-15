"""Loopback development account slice: Supabase Auth + RLS, opaque encrypted Redis sessions.

This module does not enable production ingestion or use a service-role key.
"""

import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

router = APIRouter(prefix="/account", tags=["Supabase development account"])
COOKIE = "cv_account"
SESSION_TTL = 8 * 3600


class AccountConfig(BaseModel):
    url: str = Field(pattern=r"^https://[a-z0-9]{20}\.supabase\.co$")
    publishable_key: SecretStr
    session_key: SecretStr
    enabled: Literal[True]


def config() -> AccountConfig | None:
    path = Path(os.getenv("CERTVAULT_ACCOUNT_CONFIG", ".local/supabase.json"))
    if not path.is_file():
        return None
    try:
        return AccountConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(503, "Development account configuration needs attention") from exc


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: SecretStr


class AccountProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=80)
    download_limit_bytes: int = Field(default=52428800, ge=1048576, le=104857600)


class AccountCertificateEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    issuer: str = Field(max_length=100)
    favorite: bool


class Gateway:
    def __init__(self, settings: AccountConfig, client: httpx.AsyncClient, sessions):
        self.config, self.client, self.sessions = settings, client, sessions
        self.cipher = Fernet(settings.session_key.get_secret_value().encode())

    async def request(self, method, path, *, token=None, body=None, params=None):
        headers = {"apikey": self.config.publishable_key.get_secret_value()}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if path.startswith("/rest/v1/"):
            headers["Prefer"] = "return=representation"
        try:
            async with self.client.stream(
                method,
                self.config.url + path,
                headers=headers,
                json=body,
                params=params,
                follow_redirects=False,
                timeout=15,
            ) as response:
                if response.status_code == 429:
                    raise HTTPException(429, "Too many requests. Please wait and try again.")
                if response.status_code in (400, 401, 403, 422):
                    raise HTTPException(
                        401,
                        "Account authorization failed. Check your credentials or sign in again.",
                    )
                if not 200 <= response.status_code < 300:
                    raise HTTPException(503, "Account service unavailable. Please retry.")
                content, count = [], 0
                async for chunk in response.aiter_bytes(65536):
                    count += len(chunk)
                    if count > 2 * 1024 * 1024:
                        raise HTTPException(502, "Account response exceeded its limit")
                    content.append(chunk)
        except httpx.RequestError as exc:
            raise HTTPException(503, "Account service unavailable. Please retry.") from exc
        try:
            return json.loads(b"".join(content)) if count else None
        except ValueError as exc:
            raise HTTPException(502, "Invalid account service response") from exc

    async def store(self, session_id, tokens, user_id):
        payload = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": time.time() + min(int(tokens.get("expires_in", 3600)), SESSION_TTL),
            "user_id": user_id,
        }
        await self.sessions.setex(
            "cv:session:" + session_id,
            SESSION_TTL,
            self.cipher.encrypt(json.dumps(payload).encode()),
        )

    async def load(self, session_id):
        value = await self.sessions.get("cv:session:" + session_id)
        if not value:
            raise HTTPException(401, "Please sign in to your development account")
        try:
            return json.loads(self.cipher.decrypt(value))
        except (InvalidToken, ValueError) as exc:
            raise HTTPException(401, "Account session is invalid. Please sign in again.") from exc

    async def identity(self, request):
        sid = request.cookies.get(COOKIE, "")
        if not sid or len(sid) > 128:
            raise HTTPException(401, "Please sign in to your development account")
        try:
            saved = await self.load(sid)
            if saved["expires_at"] < time.time() + 30:
                async with self.sessions.lock("cv:refresh:" + sid, timeout=20, blocking_timeout=4):
                    saved = await self.load(sid)
                    if saved["expires_at"] < time.time() + 30:
                        tokens = await self.request(
                            "POST",
                            "/auth/v1/token",
                            params={"grant_type": "refresh_token"},
                            body={"refresh_token": saved["refresh_token"]},
                        )
                        await self.store(sid, tokens, saved["user_id"])
                        saved = await self.load(sid)
            user = await self.request("GET", "/auth/v1/user", token=saved["access_token"])
            user_id = str(uuid.UUID(user["id"]))
            if user_id != saved["user_id"]:
                raise HTTPException(401, "Account session owner mismatch")
            return sid, user_id, saved["access_token"]
        except RedisError as exc:
            raise HTTPException(503, "Account session service unavailable. Please retry.") from exc
        except HTTPException as exc:
            if exc.status_code == 401:
                await self.sessions.delete("cv:session:" + sid)
            raise


async def gateway():
    settings = config()
    if not settings:
        raise HTTPException(503, "Supabase development accounts are not configured")
    sessions = Redis.from_url(
        os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    async with httpx.AsyncClient() as client:
        try:
            yield Gateway(settings, client, sessions)
        finally:
            await sessions.aclose()


@router.get("/config")
def account_config():
    return {
        "configured": config() is not None,
        "environment": "development",
        "uploads_enabled": False,
    }


@router.post("/login")
async def login(body: Credentials, response: Response, g: Gateway = Depends(gateway)):
    from apps.api.domain import digest

    rate_key = "cv:login:" + digest(body.email.strip().casefold().encode())
    try:
        attempts = await g.sessions.incr(rate_key)
        if attempts == 1:
            await g.sessions.expire(rate_key, 60)
        if attempts > 5:
            raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.")
        tokens = await g.request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            body={"email": body.email, "password": body.password.get_secret_value()},
        )
        user = await g.request("GET", "/auth/v1/user", token=tokens["access_token"])
        user_id = str(uuid.UUID(user["id"]))
        sid = secrets.token_urlsafe(32)
        await g.store(sid, tokens, user_id)
    except RedisError as exc:
        raise HTTPException(503, "Account session service unavailable. Please retry.") from exc
    response.set_cookie(
        COOKIE, sid, httponly=True, samesite="strict", max_age=SESSION_TTL, path="/"
    )
    return {"authenticated": True, "id": user_id, "environment": "development"}


@router.get("/status")
async def status(request: Request, g: Gateway = Depends(gateway)):
    if not request.cookies.get(COOKIE):
        return {"authenticated": False, "environment": "development"}
    try:
        _, user_id, _ = await g.identity(request)
        return {"authenticated": True, "id": user_id, "environment": "development"}
    except HTTPException as exc:
        if exc.status_code == 401:
            return {"authenticated": False, "environment": "development"}
        raise


@router.post("/logout")
async def logout(request: Request, response: Response, g: Gateway = Depends(gateway)):
    sid = request.cookies.get(COOKIE, "")
    confirmed = False
    try:
        if sid:
            saved = await g.load(sid)
            await g.request(
                "POST", "/auth/v1/logout", token=saved["access_token"], params={"scope": "local"}
            )
        confirmed = True
    except (HTTPException, RedisError):
        pass
    finally:
        if sid:
            try:
                await g.sessions.delete("cv:session:" + sid)
            except RedisError:
                confirmed = False
        response.delete_cookie(COOKIE, path="/")
    return {"ok": True, "provider_revocation_confirmed": confirmed}


@router.get("/profile")
async def profile(request: Request, g: Gateway = Depends(gateway)):
    _, user_id, token = await g.identity(request)
    records = await g.request(
        "GET",
        "/rest/v1/profiles",
        token=token,
        params={
            "owner_id": "eq." + user_id,
            "select": "display_name,download_limit_bytes",
            "limit": "1",
        },
    )
    return (
        records[0]
        if records
        else {"display_name": "Your workspace", "download_limit_bytes": 52428800}
    )


@router.put("/profile")
async def save_profile(body: AccountProfile, request: Request, g: Gateway = Depends(gateway)):
    _, user_id, token = await g.identity(request)
    existing = await g.request(
        "GET",
        "/rest/v1/profiles",
        token=token,
        params={"owner_id": "eq." + user_id, "select": "owner_id", "limit": "1"},
    )
    if existing:
        await g.request(
            "PATCH",
            "/rest/v1/profiles",
            token=token,
            params={"owner_id": "eq." + user_id},
            body=body.model_dump(),
        )
    else:
        await g.request(
            "POST",
            "/rest/v1/profiles",
            token=token,
            body={"owner_id": user_id, **body.model_dump()},
        )
    return {"ok": True}


@router.get("/certificates")
async def certificates(
    request: Request, q: str = Query(default="", max_length=200), g: Gateway = Depends(gateway)
):
    _, user_id, token = await g.identity(request)
    params = {
        "owner_id": "eq." + user_id,
        "trashed_at": "is.null",
        "select": "id,title,issuer,category,source,favorite,issued_on,created_at",
        "order": "created_at.desc",
        "limit": "100",
    }
    if q.strip():
        params["search_document"] = "wfts(simple)." + q.strip()
    return await g.request("GET", "/rest/v1/certificates", token=token, params=params)


@router.patch("/certificates/{key}")
async def update_certificate(
    key: uuid.UUID, body: AccountCertificateEdit, request: Request, g: Gateway = Depends(gateway)
):
    _, user_id, token = await g.identity(request)
    result = await g.request(
        "PATCH",
        "/rest/v1/certificates",
        token=token,
        params={"id": "eq." + str(key), "owner_id": "eq." + user_id},
        body=body.model_dump(),
    )
    if not result:
        raise HTTPException(404, "Certificate not found")
    return {"ok": True}
