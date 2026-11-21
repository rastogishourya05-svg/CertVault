"""Authenticated development automation controls. No live calls with default configuration."""

import base64
import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.exceptions import RedisError

from apps.api.account import COOKIE, Gateway, gateway
from apps.api.domain import STORAGE_HARD_CAP as HARD_CAP
from apps.api.domain import digest
from apps.api.pipeline_config import load_pipeline
from apps.api.pipeline_store import PipelineStore
from apps.api.postgres import DatabaseError
from apps.api.providers import GmailAdapter, ProviderUnavailable, TokenCipher, exchange_code

router = APIRouter(prefix="/account/pipeline", tags=["Authenticated ingestion"])


def configured_settings():
    try:
        value = load_pipeline()
    except (ValueError, OSError):
        raise HTTPException(
            503, "Pipeline configuration is invalid; contact the developer"
        ) from None
    if not value:
        raise HTTPException(503, "Local pipeline configuration is required")
    return value


def settings():
    value = configured_settings()
    if not value.live_imports_enabled:
        raise HTTPException(
            503, "Live imports are disabled pending configuration and security verification"
        )
    return value


async def context(request: Request, g: Gateway = Depends(gateway)):
    sid, owner, token = await g.identity(request)
    value = settings()
    return value, PipelineStore(value.database_url.get_secret_value(), owner), g, token, sid


async def dispatch_manual_job(g, owner, job, access_token):
    """Give one manually queued worker job a short-lived encrypted user JWT.

    The Celery payload contains identifiers only. The token exists in Redis for
    at most one hour and is encrypted with the server-side account session key.
    """
    key = f"cv:ingestion-session:{owner}:{job}"
    try:
        await g.sessions.setex(key, 3600, g.cipher.encrypt(access_token.encode()))
        from apps.worker.celery_app import ingest_mailbox

        ingest_mailbox.apply_async(args=[str(owner), str(job)], queue="ingestion")
    except Exception:
        try:
            await g.sessions.delete(key)
        except RedisError:
            pass
        raise HTTPException(503, "The import worker is unavailable. Please retry.") from None


async def throttle(g, owner, kind):
    try:
        key = "cv:pipeline-rate:" + kind + ":" + owner
        count = await g.sessions.incr(key)
        if count == 1:
            await g.sessions.expire(key, 60)
        if count > 6:
            raise HTTPException(429, "Too many mailbox requests. Try again in a minute.")
    except RedisError:
        raise HTTPException(503, "Mailbox rate-limit service unavailable") from None


class ConnectMailbox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: bool
    scan_days: int = Field(default=30, ge=1, le=3650)
    automatic: bool = False

    @field_validator("automatic")
    @classmethod
    def mvp_is_manual_only(cls, value):
        if value:
            raise ValueError("Automatic scans are disabled in the hackathon MVP")
        return False


class ImportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


@router.get("/status")
async def pipeline_status(request: Request, g: Gateway = Depends(gateway)):
    _, owner, _ = await g.identity(request)
    try:
        config = load_pipeline()
    except (ValueError, OSError):
        config = None
    if not config or not config.live_imports_enabled:
        return {
            "enabled": False,
            "reason": "Live imports await database/Storage credentials, Gmail OAuth, scanner and isolated parser verification.",
            "connections": [],
            "jobs": [],
            "imports": [],
            "notifications": [],
        }
    try:
        state = PipelineStore(config.database_url.get_secret_value(), owner).snapshot()
    except DatabaseError:
        raise HTTPException(503, "Pipeline database unavailable or migration not applied") from None
    return jsonable_encoder(
        {
            "enabled": True,
            "reason": "PDF imports support English OCR. Review extracted details against the issuer's record.",
            **state,
        }
    )


@router.post("/gmail/authorize")
async def authorize(body: ConnectMailbox, response: Response, ctx=Depends(context)):
    config, store, g, _, sid = ctx
    await throttle(g, store.owner, "authorize")
    if not body.consent:
        raise HTTPException(422, "Explicit mailbox read consent is required")
    state, binding, verifier = (
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(64),
    )
    # Authenticated session ID is provided by the dependency separately; no tokens in state URLs.
    return await _authorize(config, store, g, body, response, state, binding, verifier, sid)


async def _authorize(config, store, g, body, response, state, binding, verifier, sid):
    # Session-bound proof persists through a cross-site top-level callback (Lax cookie).
    payload = {
        "owner": store.owner,
        "binding": hashlib.sha256(binding.encode()).hexdigest(),
        "sid": sid,
        "verifier": verifier,
        "days": body.scan_days,
        "automatic": body.automatic,
    }
    # Store only encrypted verifier and authorization context in Redis.
    try:
        await g.sessions.setex(
            "cv:oauth:" + hashlib.sha256(state.encode()).hexdigest(),
            600,
            g.cipher.encrypt(json.dumps(payload).encode()),
        )
    except RedisError:
        raise HTTPException(503, "Authorization state service unavailable") from None
    response.set_cookie(
        "cv_mail_oauth", binding, httponly=True, samesite="lax", max_age=600, path="/"
    )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return {
        "url": config.oauth().authorize_endpoint
        + "?"
        + urlencode(
            {
                "client_id": config.google_client_id,
                "redirect_uri": config.redirect_uri,
                "response_type": "code",
                "scope": config.oauth().scope,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    }


@router.get("/gmail/callback")
async def callback(
    request: Request,
    state: str = Query(max_length=200),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = Query(default=None, max_length=200),
    g: Gateway = Depends(gateway),
):
    config = settings()
    key = "cv:oauth:" + hashlib.sha256(state.encode()).hexdigest()
    try:
        encrypted = await g.sessions.get(key)
        if not encrypted:
            raise ValueError()
        payload = json.loads(g.cipher.decrypt(encrypted))
        if not secrets.compare_digest(
            payload["binding"],
            hashlib.sha256(request.cookies.get("cv_mail_oauth", "").encode()).hexdigest(),
        ):
            raise ValueError()
        # One-use authorization state. GETDEL is atomic under concurrent callback replays.
        if not await g.sessions.getdel(key):
            raise ValueError()
        if error or not code:
            raise ValueError()
        scope = dict(request.scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"cookie"] + [
            (b"cookie", (COOKIE + "=" + payload["sid"]).encode())
        ]
        _, verified_owner, _ = await g.identity(Request(scope))
        if verified_owner != payload["owner"]:
            raise ValueError()
        tokens = await exchange_code(g.client, config.oauth(), code, payload["verifier"])
        if not tokens.refresh_token:
            raise ValueError()
        store = PipelineStore(config.database_url.get_secret_value(), payload["owner"])
        profile = await GmailAdapter(g.client, tokens.access_token).profile()
        label = profile.get("emailAddress", "")
        if not label or len(label) > 254:
            raise ValueError()
        store.connect(
            label,
            TokenCipher(config.oauth_key.get_secret_value()).encrypt(store.owner, tokens),
            datetime.now(UTC) + timedelta(seconds=min(tokens.expires_in, 86400)),
            payload["days"],
            payload["automatic"],
        )
    except (
        ValueError,
        KeyError,
        InvalidToken,
        ProviderUnavailable,
        RedisError,
        DatabaseError,
        HTTPException,
    ):
        # No provider code, email or raw diagnostic reflected into HTML/URL/logs.
        response = RedirectResponse("http://127.0.0.1:3000/account?mailbox=failed", 303)
    else:
        response = RedirectResponse("http://127.0.0.1:3000/account?mailbox=connected", 303)
    response.delete_cookie("cv_mail_oauth", path="/")
    return response


class ScanRange(BaseModel):
    scan_days: int = Field(ge=1, le=3650)


@router.put("/connections/{key}/range")
async def change_scan_range(key: uuid.UUID, body: ScanRange, ctx=Depends(context)):
    _, store, g, _, _ = ctx
    await throttle(g, store.owner, "range")
    if not store.update_scan_range(key, body.scan_days):
        raise HTTPException(404, "Connected mailbox not found")
    return {"scan_days": body.scan_days}


@router.post("/connections/{key}/scan")
async def enqueue(key: uuid.UUID, ctx=Depends(context)):
    _, store, g, token, _ = ctx
    await throttle(g, store.owner, "scan")
    try:
        job = store.enqueue(key, rescan=True)
    except ValueError:
        raise HTTPException(404, "Connected mailbox not found") from None
    await dispatch_manual_job(g, store.owner, job, token)
    return {"job_id": job, "status": "queued"}


@router.post("/imports/{key}/review")
async def resolve_review(key: uuid.UUID, dismissed: bool = False, ctx=Depends(context)):
    _, store, _, _, _ = ctx
    if not store.resolve_review(key, dismissed):
        raise HTTPException(409, "Review unavailable or already resolved")
    return {"ok": True}


@router.post("/imports/{key}/decision")
async def decision(key: uuid.UUID, body: ImportDecision, ctx=Depends(context)):
    _, store, g, token, _ = ctx
    row = store.decide(key, body.approve)
    if not row:
        raise HTTPException(409, "Approval item not found or already decided")
    if body.approve:
        job = store.enqueue(row["connection_id"])
        await dispatch_manual_job(g, store.owner, job, token)
    return {"ok": True}


@router.delete("/connections/{key}")
async def disconnect(key: uuid.UUID, ctx=Depends(context)):
    config, store, g, _, sid = ctx
    connection = store.connection(key)
    if not connection:
        raise HTTPException(404, "Mailbox not found")
    # Stop local work/remove stored credentials regardless of provider availability.
    store.disconnect(key)
    confirmed = False
    try:
        cipher = TokenCipher(config.oauth_key.get_secret_value())
        tokens = cipher.decrypt(store.owner, bytes(connection["ciphertext"]))
        token = (tokens.refresh_token or tokens.access_token).get_secret_value()
        response = await g.client.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            timeout=15,
            follow_redirects=False,
        )
        confirmed = response.status_code == 200
    except (httpx.RequestError, InvalidToken, ProviderUnavailable):
        pass
    return {"ok": True, "provider_revocation_confirmed": confirmed}


@router.get("/certificates/{key}/download")
async def download(
    key: uuid.UUID,
    request: Request,
    inline: bool = Query(default=False),
    g: Gateway = Depends(gateway),
):
    config = configured_settings()
    _, owner, token = await g.identity(request)
    store = PipelineStore(config.database_url.get_secret_value(), owner)
    with store.db() as db:
        row = db.execute(
            "select f.object_path,f.bytes,f.sha256 from public.certificate_files f join public.certificates c on c.id=f.certificate_id and c.owner_id=f.owner_id where c.id=%s and c.owner_id=%s and c.trashed_at is null",
            (key, owner),
        ).fetchone()
    if not row or not row["object_path"].startswith(owner + "/"):
        raise HTTPException(404, "Certificate not found")
    # Download with user's JWT, so Storage RLS independently enforces ownership.
    # Context has already verified Auth; acquire its token without sending it to the browser.
    try:
        async with g.client.stream(
            "GET",
            g.config.url + "/storage/v1/object/authenticated/certificates/" + row["object_path"],
            headers={
                "apikey": g.config.publishable_key.get_secret_value(),
                "Authorization": "Bearer " + token,
            },
            timeout=45,
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise HTTPException(503, "Private download unavailable")
            data = bytearray()
            async for chunk in response.aiter_bytes(65536):
                if len(data) + len(chunk) > min(row["bytes"], HARD_CAP):
                    raise HTTPException(503, "Stored file size mismatch")
                data.extend(chunk)
        if len(data) != row["bytes"] or digest(bytes(data)) != row["sha256"]:
            raise HTTPException(503, "Stored file size mismatch")
    except httpx.RequestError:
        raise HTTPException(503, "Private download unavailable") from None
    from apps.api.documents import FORMATS, extension

    suffix = extension(data)
    return Response(
        bytes(data),
        media_type=FORMATS[suffix],
        headers={
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="certificate{suffix}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


class ExportSelection(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


@router.post("/export")
async def export_vault(selection: ExportSelection, request: Request, g: Gateway = Depends(gateway)):
    """Assemble and verify an owner-authorized archive before releasing any bytes."""
    import tempfile
    import zipfile

    from starlette.responses import StreamingResponse

    from apps.api.documents import extension

    _, owner, token = await g.identity(request)
    output = tempfile.TemporaryFile()
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            offset = 0
            metadata = []
            while True:
                params = {
                    "owner_id": "eq." + owner,
                    "trashed_at": "is.null",
                    "order": "id",
                    "limit": "100",
                    "offset": str(offset),
                    "select": "id,title,issuer,recipient,issued_on,expires_on,category,credential_id,verification_url,source,favorite,reviewed_at,collection_items(collections(name)),certificate_tags(tags(name))",
                }
                if selection.ids:
                    params["id"] = "in.(" + ",".join(map(str, selection.ids)) + ")"
                rows = await g.request("GET", "/rest/v1/certificates", token=token, params=params)
                for row in rows:
                    file = await download(uuid.UUID(row["id"]), request, False, g)
                    if output.tell() + len(file.body) > 512 * 1024 * 1024:
                        raise HTTPException(
                            413,
                            "Archive exceeds 512 MiB. Select fewer files and export in batches.",
                        )
                    name = f"files/{row['id']}{extension(file.body)}"
                    archive.writestr(name, file.body)
                    metadata.append({**row, "file": name})
                offset += len(rows)
                if len(rows) < 100:
                    break
            archive.writestr(
                "certificates.json", json.dumps(metadata, ensure_ascii=False, indent=2)
            )
        output.seek(0)
    except BaseException:
        output.close()
        raise

    def chunks():
        try:
            while block := output.read(65536):
                yield block
        finally:
            output.close()

    from starlette.background import BackgroundTask

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        background=BackgroundTask(output.close),
        headers={
            "Content-Disposition": 'attachment; filename="certvault.zip"',
            "Cache-Control": "no-store",
        },
    )
