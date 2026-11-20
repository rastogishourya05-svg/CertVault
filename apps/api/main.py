import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from apps.api.account import router as account_router
from apps.api.domain import (
    HARD_CAP,
    MIB,
    HardLimitExceeded,
    PolicyError,
    bounded_bytes,
    digest,
    size_decision,
)
from apps.api.limits import BodyLimitMiddleware
from apps.api.pipeline_routes import router as pipeline_router
from apps.api.postgres import DatabaseError
from apps.api.processing import extract_pdf, sample_pdf
from apps.api.store import data_dir, db, initialize, profile_view, rows


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(UTC).isoformat()


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("CERTVAULT_MODE", "demo") != "demo":
        raise RuntimeError(
            "Live mode is disabled until Supabase, scanning and OAuth release gates pass"
        )
    initialize()
    yield


app = FastAPI(title="CertVault API", version="0.1.0", lifespan=lifespan)
app.include_router(account_router)
app.include_router(pipeline_router)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.exception_handler(RequestValidationError)
async def safe_input_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/account/"):
        return JSONResponse({"detail": "One or more account fields are invalid."}, status_code=422)
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(DatabaseError)
async def safe_database_error(request: Request, exc: DatabaseError):
    return RawResponse(
        '{"detail":"Pipeline database unavailable; retry or check configuration"}',
        status_code=503,
        media_type="application/json",
    )


@app.middleware("http")
async def demo_boundary(request: Request, call_next):
    if request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
        return RawResponse("Local demonstration only", status_code=403)
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin not in ("http://127.0.0.1:3000", "http://localhost:3000")
    ):
        return RawResponse("Origin denied", status_code=403)
    result = await call_next(request)
    result.headers["Cache-Control"] = "no-store"
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "no-referrer"
    return result


def owner(request: Request) -> str:
    token = request.cookies.get("cv_session", "")
    with db() as c:
        row = c.execute(
            "SELECT owner FROM sessions WHERE token=? AND expires>?",
            (digest(token.encode()), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Start a local demo session to continue")
    return row["owner"]


def audit(c, user, event):
    c.execute("INSERT INTO audit VALUES (?,?,?,?)", (uid(), user, event, now()))


def notify(c, user, key, message):
    c.execute(
        "INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,0,?)",
        (uid(), user, key, message, now()),
    )


def owned(c, table, key, user):
    # Table names come only from static internal call sites.
    row = c.execute(f"SELECT * FROM {table} WHERE id=? AND owner=?", (key, user)).fetchone()
    if row is None:
        raise HTTPException(404, "Resource not found")
    return row


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Certificate(StrictModel):
    id: str
    title: str
    issuer: str
    issued: str | None
    category: str
    source: str
    bytes: int
    favorite: bool
    trashed: bool
    created: str
    tags: list[str] = Field(default_factory=list)


def certificate(row):
    values = {key: row[key] for key in Certificate.model_fields if key != "tags"}
    return Certificate(**values, tags=json.loads(row["tags"]))


class EditCertificate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    issuer: str = Field(min_length=1, max_length=100)
    category: Literal["Technology", "Design", "Business", "Other"]
    issued: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values):
        normalized = list(dict.fromkeys(v.strip().casefold() for v in values))
        if any(not v or len(v) > 30 for v in normalized):
            raise ValueError("Each tag must contain 1–30 characters")
        return normalized


class CollectionInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    certificate_ids: list[str] = Field(default_factory=list, max_length=100)


class BulkInput(StrictModel):
    certificate_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["favorite", "trash", "restore"]


class Toggle(StrictModel):
    value: bool


class ConnectionInput(StrictModel):
    provider: Literal["gmail", "outlook"]
    consent: Literal[True]


class SettingsInput(StrictModel):
    threshold_mib: int = Field(ge=1, le=100)
    name: str = Field(min_length=1, max_length=80)


class ShareInput(StrictModel):
    certificate_id: str
    expires_hours: int = Field(default=24, ge=1, le=168)
    consent: Literal[True]


class ProfileInput(StrictModel):
    enabled: bool
    name: str = Field(min_length=1, max_length=80)
    slug: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")
    featured: list[str] = Field(max_length=20)
    consent: Literal[True]


class DraftInput(StrictModel):
    certificate_id: str
    tone: Literal["professional", "friendly", "short"]


class DraftEdit(StrictModel):
    content: str = Field(min_length=1, max_length=3000)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "demo",
        "mail": "synthetic",
        "ai": "unconfigured",
        "scanner": "unconfigured",
    }


@app.post("/auth/demo")
def start_demo(request: Request, response: Response):
    # Reuse a live session; starting again never silently discards a user's demo vault.
    try:
        user = owner(request)
        return {"id": user, "mode": "demo"}
    except HTTPException:
        pass
    token, user = secrets.token_urlsafe(32), uid()
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        c.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (digest(token.encode()), user, time.time() + 86400),
        )
        c.execute("INSERT INTO settings(owner) VALUES (?)", (user,))
        audit(c, user, "Local demo session started")
    response.set_cookie(
        "cv_session", token, httponly=True, samesite="strict", max_age=86400, path="/"
    )
    return {"id": user, "mode": "demo"}


@app.delete("/auth/session")
def sign_out(request: Request, response: Response, user=Depends(owner)):
    with db() as c:
        c.execute(
            "DELETE FROM sessions WHERE token=? AND owner=?",
            (digest(request.cookies["cv_session"].encode()), user),
        )
    response.delete_cookie("cv_session", path="/")
    return {"ok": True}


@app.get("/auth/me")
def me(user=Depends(owner)):
    return {"id": user, "mode": "demo"}


@app.get("/auth/status")
def session_status(request: Request):
    try:
        return {"authenticated": True, "id": owner(request), "mode": "demo"}
    except HTTPException:
        return {"authenticated": False, "mode": "demo"}


@app.get("/certificates", response_model=list[Certificate])
def list_certificates(
    q: str = Query(default="", max_length=200), trashed: bool = False, user=Depends(owner)
):
    with db() as c:
        result = c.execute(
            "SELECT * FROM certificates WHERE owner=? AND trashed=? ORDER BY created DESC",
            (user, int(trashed)),
        ).fetchall()
        return [
            certificate(r)
            for r in result
            if q.strip().casefold()
            in f"{r['title']} {r['issuer']} {r['category']} {r['text']} {r['tags']}".casefold()
        ]


@app.get("/certificates/{key}", response_model=Certificate)
def get_certificate(key: str, user=Depends(owner)):
    with db() as c:
        return certificate(owned(c, "certificates", key, user))


def save_certificate(c, user, data, title, issuer, category, source):
    hash_value = digest(data)
    existing = c.execute(
        "SELECT id FROM certificates WHERE owner=? AND hash=?", (user, hash_value)
    ).fetchone()
    if existing:
        notify(
            c,
            user,
            f"duplicate:{hash_value}",
            "Duplicate detected. Your existing certificate was kept.",
        )
        return existing["id"], True
    text = extract_pdf(data)
    key = uid()
    folder = data_dir() / "files" / user
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.pdf"
    path.write_bytes(data)
    try:
        c.execute(
            "INSERT INTO certificates(id,owner,title,issuer,issued,category,source,hash,bytes,favorite,trashed,created,text) VALUES (?,?,?,?,NULL,?,?,?,?,0,0,?,?)",
            (key, user, title, issuer, category, source, hash_value, len(data), now(), text),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    notify(c, user, f"stored:{key}", f"{title} was added to your private vault.")
    audit(c, user, "Certificate stored privately (local demonstration)")
    return key, False


@app.post("/certificates/upload")
async def upload(file: UploadFile = File(), user=Depends(owner)):
    with db() as c:
        threshold = c.execute("SELECT threshold FROM settings WHERE owner=?", (user,)).fetchone()[0]
    try:
        chunks, count = [], 0
        while chunk := await file.read(64 * 1024):
            count += len(chunk)
            if count > HARD_CAP:
                raise HardLimitExceeded("File exceeds the 100 MiB local demonstration limit.")
            if count > threshold:
                raise PolicyError(
                    "Upload exceeds your configured auto-download limit. Raise it in Settings before retrying."
                )
            chunks.append(chunk)
        data = bounded_bytes(chunks, threshold)
        title = (file.filename or "Untitled certificate").rsplit(".", 1)[0][
            :160
        ] or "Untitled certificate"
        with db() as c:
            key, duplicate = save_certificate(
                c, user, data, title, "Needs review", "Other", "Manual upload"
            )
        return {"id": key, "duplicate": duplicate, "review_required": True}
    except PolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()


@app.patch("/certificates/{key}", response_model=Certificate)
def edit_certificate(key: str, body: EditCertificate, user=Depends(owner)):
    if body.issued:
        try:
            datetime.strptime(body.issued, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(422, "Invalid calendar date") from exc
    with db() as c:
        owned(c, "certificates", key, user)
        c.execute(
            "UPDATE certificates SET title=?,issuer=?,category=?,issued=?,tags=? WHERE id=? AND owner=?",
            (body.title, body.issuer, body.category, body.issued, json.dumps(body.tags), key, user),
        )
        audit(c, user, "Certificate metadata updated")
        return certificate(owned(c, "certificates", key, user))


@app.put("/certificates/{key}/favorite")
def favorite(key: str, body: Toggle, user=Depends(owner)):
    with db() as c:
        owned(c, "certificates", key, user)
        c.execute(
            "UPDATE certificates SET favorite=? WHERE id=? AND owner=?", (body.value, key, user)
        )
    return {"ok": True}


@app.put("/certificates/{key}/trash")
def trash(key: str, body: Toggle, user=Depends(owner)):
    with db() as c:
        owned(c, "certificates", key, user)
        c.execute(
            "UPDATE certificates SET trashed=? WHERE id=? AND owner=?", (body.value, key, user)
        )
        if body.value:
            c.execute("UPDATE shares SET revoked=1 WHERE certificate_id=? AND owner=?", (key, user))
            profile = c.execute(
                "SELECT featured FROM public_profiles WHERE owner=?", (user,)
            ).fetchone()
            if profile:
                featured = [item for item in json.loads(profile["featured"]) if item != key]
                c.execute(
                    "UPDATE public_profiles SET featured=? WHERE owner=?",
                    (json.dumps(featured), user),
                )
        audit(c, user, "Certificate moved to trash" if body.value else "Certificate restored")
    return {"ok": True}


def pdf_response(row, inline=False):
    path = data_dir() / "files" / row["owner"] / f"{row['id']}.pdf"
    if not path.is_file():
        raise HTTPException(404, "File unavailable")
    return RawResponse(
        path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{'inline' if inline else 'attachment'}; filename=certificate.pdf",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "no-store",
        },
    )


@app.get("/certificates/{key}/download")
def download(key: str, inline: bool = False, user=Depends(owner)):
    with db() as c:
        row = owned(c, "certificates", key, user)
        if row["trashed"]:
            raise HTTPException(404, "Restore this certificate first")
        return pdf_response(row, inline)


@app.get("/connections")
def connections(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute("SELECT id,provider,active,created FROM connections WHERE owner=?", (user,))
        )


@app.post("/connections")
def connect(body: ConnectionInput, user=Depends(owner)):
    with db() as c:
        c.execute(
            "INSERT INTO connections VALUES (?,?,?,1,?) ON CONFLICT(owner,provider) DO UPDATE SET active=1",
            (uid(), user, body.provider, now()),
        )
        audit(c, user, f"Consented to synthetic {body.provider} mailbox demonstration")
    return {
        "mode": "demo",
        "message": "Sample mailbox connected. No external account was accessed.",
    }


@app.delete("/connections/{key}")
def disconnect(key: str, user=Depends(owner)):
    with db() as c:
        owned(c, "connections", key, user)
        c.execute("UPDATE connections SET active=0 WHERE id=? AND owner=?", (key, user))
        c.execute(
            "UPDATE imports SET status='rejected' WHERE connection_id=? AND owner=? AND status IN ('eligible','awaiting_approval')",
            (key, user),
        )
        audit(c, user, "Mailbox disconnected; existing certificates retained")
    return {"ok": True}


SAMPLES = [
    ("cloud", "Cloud Architecture Foundations", "Northstar Academy", "Technology", 24000),
    ("design", "Human-Centered Design", "Forma Institute", "Design", 18000),
    ("data", "Data Analytics Essentials", "Open Learning Lab", "Technology", 21000),
    ("large", "Advanced Leadership Program", "Horizon School", "Business", 51 * MIB),
]


def process_import(c, item, approved=False):
    connection = owned(c, "connections", item["connection_id"], item["owner"])
    if not connection["active"]:
        raise HTTPException(409, "Mailbox disconnected")
    threshold = c.execute(
        "SELECT threshold FROM settings WHERE owner=?", (item["owner"],)
    ).fetchone()[0]
    status = size_decision(item["declared_size"], threshold, approved)
    if status == "eligible":
        data = sample_pdf(item["title"], item["issuer"])
        # Exercise the real byte bound for the synthetic oversized fixture.
        if item["source_key"] == "large":
            data += b" " * (item["declared_size"] - len(data))
        data = bounded_bytes(
            (data[i : i + 65536] for i in range(0, len(data), 65536)), threshold, approved
        )
        key, duplicate = save_certificate(
            c,
            item["owner"],
            data,
            item["title"],
            item["issuer"],
            item["category"],
            f"Sample {connection['provider']}",
        )
        status = "duplicate" if duplicate else "stored"
        c.execute(
            "UPDATE imports SET certificate_id=? WHERE id=? AND owner=?",
            (key, item["id"], item["owner"]),
        )
    else:
        notify(
            c,
            item["owner"],
            f"approval:{item['id']}",
            f"{item['title']} needs your download approval (51 MiB).",
        )
    c.execute(
        "UPDATE imports SET status=? WHERE id=? AND owner=?", (status, item["id"], item["owner"])
    )


@app.post("/connections/{key}/sync")
def sync(key: str, user=Depends(owner)):
    with db() as c:
        connection = owned(c, "connections", key, user)
        if not connection["active"]:
            raise HTTPException(409, "Reconnect this mailbox first")
        threshold = c.execute("SELECT threshold FROM settings WHERE owner=?", (user,)).fetchone()[0]
        for source, title, issuer, category, size in SAMPLES:
            c.execute(
                "INSERT OR IGNORE INTO imports VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                (
                    uid(),
                    user,
                    key,
                    source,
                    title,
                    issuer,
                    category,
                    size,
                    size_decision(size, threshold),
                ),
            )
        pending = c.execute(
            "SELECT * FROM imports WHERE owner=? AND connection_id=? AND status IN ('eligible','awaiting_approval')",
            (user, key),
        ).fetchall()
        for item in pending:
            process_import(c, item)
        audit(c, user, "Synthetic fixture scan completed")
    return {"ok": True, "mode": "demo"}


@app.get("/imports")
def imports(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute(
                "SELECT id,title,issuer,declared_size,status,certificate_id FROM imports WHERE owner=? ORDER BY rowid DESC",
                (user,),
            )
        )


@app.post("/imports/{key}/approve")
def approve(key: str, user=Depends(owner)):
    with db() as c:
        item = owned(c, "imports", key, user)
        if item["status"] != "awaiting_approval":
            raise HTTPException(409, "This import is no longer awaiting approval")
        process_import(c, item, approved=True)
        audit(c, user, "Approved one specific oversized sample import")
    return {"ok": True}


@app.post("/imports/{key}/reject")
def reject(key: str, user=Depends(owner)):
    with db() as c:
        item = owned(c, "imports", key, user)
        if item["status"] != "awaiting_approval":
            raise HTTPException(409, "This import is no longer awaiting approval")
        c.execute("UPDATE imports SET status='rejected' WHERE id=? AND owner=?", (key, user))
        audit(c, user, "Rejected oversized import; no file stored")
    return {"ok": True}


@app.get("/notifications")
def notifications(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute(
                "SELECT id,message,read,created FROM notifications WHERE owner=? ORDER BY created DESC",
                (user,),
            )
        )


@app.put("/notifications/read")
def read_notifications(user=Depends(owner)):
    with db() as c:
        c.execute("UPDATE notifications SET read=1 WHERE owner=?", (user,))
    return {"ok": True}


@app.get("/audit")
def history(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute(
                "SELECT id,event,created FROM audit WHERE owner=? ORDER BY created DESC LIMIT 100",
                (user,),
            )
        )


@app.get("/settings")
def settings(user=Depends(owner)):
    with db() as c:
        row = c.execute("SELECT * FROM settings WHERE owner=?", (user,)).fetchone()
        return {
            "threshold_mib": row["threshold"] // MIB,
            "name": row["name"],
            "hard_cap_bytes": HARD_CAP,
        }


@app.put("/settings")
def save_settings(body: SettingsInput, user=Depends(owner)):
    with db() as c:
        c.execute(
            "UPDATE settings SET threshold=?,name=? WHERE owner=?",
            (body.threshold_mib * MIB, body.name, user),
        )
        audit(c, user, "Download preference updated")
    return {"ok": True}


@app.post("/shares")
def create_share(body: ShareInput, user=Depends(owner)):
    token, key = secrets.token_urlsafe(32), uid()
    expires = time.time() + body.expires_hours * 3600
    with db() as c:
        row = owned(c, "certificates", body.certificate_id, user)
        if row["trashed"]:
            raise HTTPException(409, "Restore the certificate first")
        c.execute(
            "INSERT INTO shares VALUES (?,?,?,?,?,0)",
            (key, user, body.certificate_id, digest(token.encode()), expires),
        )
        audit(c, user, "Explicitly created an expiring certificate share")
    return {"id": key, "path": f"/api/shared/{token}", "expires": expires}


@app.get("/shares")
def shares(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute(
                "SELECT s.id,s.certificate_id,s.expires,s.revoked,c.title FROM shares s JOIN certificates c ON c.id=s.certificate_id AND c.owner=s.owner WHERE s.owner=?",
                (user,),
            )
        )


@app.delete("/shares/{key}")
def revoke(key: str, user=Depends(owner)):
    with db() as c:
        owned(c, "shares", key, user)
        c.execute("UPDATE shares SET revoked=1 WHERE id=? AND owner=?", (key, user))
        audit(c, user, "Share revoked")
    return {"ok": True}


@app.get("/shared/{token}")
def shared(token: str):
    with db() as c:
        row = c.execute(
            "SELECT c.* FROM shares s JOIN certificates c ON c.id=s.certificate_id AND c.owner=s.owner WHERE s.token_hash=? AND s.revoked=0 AND s.expires>? AND c.trashed=0",
            (digest(token.encode()), time.time()),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Share expired or unavailable")
        return pdf_response(row)


@app.get("/profile")
def profile(user=Depends(owner)):
    with db() as c:
        row = c.execute("SELECT * FROM public_profiles WHERE owner=?", (user,)).fetchone()
        return profile_view(row) if row else None


@app.put("/profile")
def save_profile(body: ProfileInput, user=Depends(owner)):
    with db() as c:
        for key in body.featured:
            cert = owned(c, "certificates", key, user)
            if cert["trashed"]:
                raise HTTPException(409, "Trashed certificates cannot be featured")
        existing = c.execute(
            "SELECT owner FROM public_profiles WHERE slug=? AND owner<>?", (body.slug, user)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Profile address is already taken")
        c.execute(
            "INSERT INTO public_profiles VALUES (?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET slug=excluded.slug,enabled=excluded.enabled,name=excluded.name,featured=excluded.featured",
            (user, body.slug, body.enabled, body.name, json.dumps(body.featured)),
        )
        audit(c, user, "Public profile visibility explicitly updated")
    return {"ok": True}


@app.get("/public/{slug}")
def public_profile(slug: str):
    with db() as c:
        p = c.execute(
            "SELECT * FROM public_profiles WHERE slug=? AND enabled=1", (slug,)
        ).fetchone()
        if not p:
            raise HTTPException(404, "Profile unavailable")
        selected = set(json.loads(p["featured"]))
        certs = c.execute(
            "SELECT * FROM certificates WHERE owner=? AND trashed=0", (p["owner"],)
        ).fetchall()
        return {
            "name": p["name"],
            "certificates": [
                {"title": r["title"], "issuer": r["issuer"], "category": r["category"]}
                for r in certs
                if r["id"] in selected
            ],
        }


@app.get("/social-drafts")
def drafts(user=Depends(owner)):
    with db() as c:
        return rows(
            c.execute(
                "SELECT id,certificate_id,tone,content,created FROM drafts WHERE owner=? ORDER BY created DESC",
                (user,),
            )
        )


@app.post("/social-drafts")
def create_draft(body: DraftInput, user=Depends(owner)):
    with db() as c:
        cert = owned(c, "certificates", body.certificate_id, user)
        if cert["trashed"]:
            raise HTTPException(409, "Restore the certificate first")
        opening = {
            "professional": "A new milestone in my learning journey:",
            "friendly": "Excited to share a little win!",
            "short": "Learning milestone:",
        }[body.tone]
        content = f"{opening} {cert['title']} from {cert['issuer']}.\n\n#LifelongLearning #ProfessionalDevelopment"
        key = uid()
        c.execute(
            "INSERT INTO drafts VALUES (?,?,?,?,?,?)",
            (key, user, cert["id"], body.tone, content, now()),
        )
    return {
        "id": key,
        "content": content,
        "mode": "template",
        "message": "Local template; no AI provider or publishing service called",
    }


@app.patch("/social-drafts/{key}")
def edit_draft(key: str, body: DraftEdit, user=Depends(owner)):
    with db() as c:
        owned(c, "drafts", key, user)
        c.execute("UPDATE drafts SET content=? WHERE id=? AND owner=?", (body.content, key, user))
    return {"ok": True}


@app.get("/export")
def export(user=Depends(owner)):
    with db() as c:
        certs = [
            certificate(r).model_dump()
            for r in c.execute("SELECT * FROM certificates WHERE owner=?", (user,)).fetchall()
        ]
    return RawResponse(
        json.dumps({"certificates": certs}, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=certvault-export.json"},
    )


@app.get("/collections")
def collections(user=Depends(owner)):
    with db() as c:
        result = rows(
            c.execute(
                "SELECT id,name,created FROM collections WHERE owner=? ORDER BY created DESC",
                (user,),
            )
        )
        for item in result:
            item["certificate_ids"] = [
                r[0]
                for r in c.execute(
                    "SELECT i.certificate_id FROM collection_items i JOIN certificates cert ON cert.id=i.certificate_id WHERE i.collection_id=? AND cert.owner=? AND cert.trashed=0",
                    (item["id"], user),
                )
            ]
        return result


def set_collection_items(c, key, user, ids):
    for cert_id in set(ids):
        cert = owned(c, "certificates", cert_id, user)
        if cert["trashed"]:
            raise HTTPException(409, "Restore certificates before adding them to a collection")
    c.execute("DELETE FROM collection_items WHERE collection_id=?", (key,))
    c.executemany(
        "INSERT INTO collection_items VALUES (?,?)", [(key, cert_id) for cert_id in set(ids)]
    )


@app.post("/collections")
def create_collection(body: CollectionInput, user=Depends(owner)):
    with db() as c:
        if c.execute(
            "SELECT 1 FROM collections WHERE owner=? AND name=?", (user, body.name.strip())
        ).fetchone():
            raise HTTPException(409, "A collection with this name already exists")
        if not body.name.strip():
            raise HTTPException(422, "Enter a collection name")
        key = uid()
        c.execute("INSERT INTO collections VALUES (?,?,?,?)", (key, user, body.name.strip(), now()))
        set_collection_items(c, key, user, body.certificate_ids)
        audit(c, user, "Private collection created")
    return {"id": key}


@app.put("/collections/{key}")
def update_collection(key: str, body: CollectionInput, user=Depends(owner)):
    with db() as c:
        owned(c, "collections", key, user)
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Enter a collection name")
        if c.execute(
            "SELECT 1 FROM collections WHERE owner=? AND name=? AND id<>?", (user, name, key)
        ).fetchone():
            raise HTTPException(409, "A collection with this name already exists")
        c.execute("UPDATE collections SET name=? WHERE id=? AND owner=?", (name, key, user))
        set_collection_items(c, key, user, body.certificate_ids)
        audit(c, user, "Private collection updated")
    return {"ok": True}


@app.post("/certificates/bulk")
def bulk_certificates(body: BulkInput, user=Depends(owner)):
    with db() as c:
        for key in set(body.certificate_ids):
            owned(c, "certificates", key, user)
        for key in set(body.certificate_ids):
            if body.action == "favorite":
                c.execute("UPDATE certificates SET favorite=1 WHERE id=? AND owner=?", (key, user))
            else:
                c.execute(
                    "UPDATE certificates SET trashed=? WHERE id=? AND owner=?",
                    (body.action == "trash", key, user),
                )
                if body.action == "trash":
                    c.execute(
                        "UPDATE shares SET revoked=1 WHERE certificate_id=? AND owner=?",
                        (key, user),
                    )
        if body.action == "trash":
            profile = c.execute(
                "SELECT featured FROM public_profiles WHERE owner=?", (user,)
            ).fetchone()
            if profile:
                featured = [
                    key
                    for key in json.loads(profile["featured"])
                    if key not in body.certificate_ids
                ]
                c.execute(
                    "UPDATE public_profiles SET featured=? WHERE owner=?",
                    (json.dumps(featured), user),
                )
        audit(c, user, f"Bulk {body.action}: {len(set(body.certificate_ids))} certificates")
    return {"ok": True}
