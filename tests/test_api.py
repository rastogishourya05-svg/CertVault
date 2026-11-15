import time

from fastapi.testclient import TestClient

from apps.api.domain import digest
from apps.api.main import app
from apps.api.processing import sample_pdf
from apps.api.store import data_dir, db


def test_empty_vault_and_auth_boundary(client):
    assert client.get("/certificates").json() == []
    assert client.get("/auth/me").json()["mode"] == "demo"
    with TestClient(app) as other:
        assert other.get("/certificates").status_code == 401
        assert (
            other.post("/auth/demo", headers={"Origin": "https://evil.example"}).status_code == 403
        )


def test_discovery_dedupe_and_notification_idempotency(imported):
    client, connection = imported
    assert len(client.get("/certificates").json()) == 3
    pending = client.get("/imports").json()
    assert len(pending) == 4
    assert sum(i["status"] == "awaiting_approval" for i in pending) == 1
    before = client.get("/notifications").json()
    client.post(f"/connections/{connection['id']}/sync")
    assert len(client.get("/certificates").json()) == 3
    assert client.get("/notifications").json() == before


def test_reject_never_stores_large_file(imported):
    client, connection = imported
    item = next(i for i in client.get("/imports").json() if i["status"] == "awaiting_approval")
    assert client.post(f"/imports/{item['id']}/reject").status_code == 200
    client.post(f"/connections/{connection['id']}/sync")
    assert len(client.get("/certificates").json()) == 3
    assert len(list((data_dir() / "files").rglob("*.pdf"))) == 3
    assert client.post(f"/imports/{item['id']}/approve").status_code == 409


def test_explicit_approval_imports_only_one_file(imported):
    client, _ = imported
    item = next(i for i in client.get("/imports").json() if i["status"] == "awaiting_approval")
    assert client.post(f"/imports/{item['id']}/approve").status_code == 200
    certs = client.get("/certificates").json()
    assert len(certs) == 4
    large = next(c for c in certs if c["title"] == item["title"])
    assert large["bytes"] == 51 * 1024 * 1024
    assert client.post(f"/imports/{item['id']}/approve").status_code == 409


def test_cross_tenant_access_denied(imported):
    client, conn = imported
    cert = client.get("/certificates").json()[0]
    pending = client.get("/imports").json()[0]
    share = client.post("/shares", json={"certificate_id": cert["id"], "consent": True}).json()
    with TestClient(app) as other:
        other.post("/auth/demo")
        assert other.get("/certificates").json() == []
        assert other.get("/notifications").json() == []
        assert other.get(f"/certificates/{cert['id']}/download").status_code == 404
        assert (
            other.put(f"/certificates/{cert['id']}/favorite", json={"value": True}).status_code
            == 404
        )
        assert other.post(f"/connections/{conn['id']}/sync").status_code == 404
        assert other.post(f"/imports/{pending['id']}/approve").status_code == 404
        assert other.delete(f"/shares/{share['id']}").status_code == 404
        assert (
            other.post(
                "/social-drafts", json={"certificate_id": cert["id"], "tone": "short"}
            ).status_code
            == 404
        )


def test_disconnect_blocks_future_work(imported):
    client, conn = imported
    assert client.delete(f"/connections/{conn['id']}").status_code == 200
    assert client.post(f"/connections/{conn['id']}/sync").status_code == 409
    assert len(client.get("/certificates").json()) == 3
    assert not any(i["status"] == "awaiting_approval" for i in client.get("/imports").json())


def test_manual_upload_validation_dedupe_and_search(client):
    data = sample_pdf("Unique sample", "Issuer")
    first = client.post(
        "/certificates/upload", files={"file": ("sample.pdf", data, "application/pdf")}
    )
    assert first.status_code == 200
    assert first.json()["review_required"]
    assert client.post("/certificates/upload", files={"file": ("sample.pdf", data)}).json()[
        "duplicate"
    ]
    assert len(client.get("/certificates?q=Unique").json()) == 1
    assert (
        client.post("/certificates/upload", files={"file": ("evil.pdf", b"malware")}).status_code
        == 422
    )
    key = first.json()["id"]
    assert (
        client.patch(
            f"/certificates/{key}",
            json={
                "title": "Updated",
                "issuer": "Reviewed",
                "category": "Design",
                "issued": "2026-02-30",
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/certificates/{key}",
            json={
                "title": "Updated",
                "issuer": "Reviewed",
                "category": "Design",
                "issued": "2026-02-28",
            },
        ).status_code
        == 200
    )
    assert client.get(f"/certificates/{key}/download").content.startswith(b"%PDF-")
    assert len(client.get("/certificates?q=Updated").json()) == 1


def test_share_consent_expiry_revocation_trash(imported):
    client, _ = imported
    cert = client.get("/certificates").json()[0]
    assert client.post("/shares", json={"certificate_id": cert["id"]}).status_code == 422
    share = client.post("/shares", json={"certificate_id": cert["id"], "consent": True}).json()
    path = share["path"].removeprefix("/api")
    assert client.get(path).status_code == 200
    with db() as c:
        stored = c.execute("SELECT * FROM shares WHERE id=?", (share["id"],)).fetchone()
        assert stored["token_hash"] == digest(path.split("/")[-1].encode())
        c.execute("UPDATE shares SET expires=? WHERE id=?", (time.time() - 1, share["id"]))
    assert client.get(path).status_code == 404
    share = client.post("/shares", json={"certificate_id": cert["id"], "consent": True}).json()
    assert client.delete(f"/shares/{share['id']}").status_code == 200
    assert client.get(share["path"].removeprefix("/api")).status_code == 404
    client.put(f"/certificates/{cert['id']}/trash", json={"value": True})
    assert client.get(f"/certificates/{cert['id']}/download").status_code == 404
    assert len(client.get("/certificates?trashed=true").json()) == 1
    client.put(f"/certificates/{cert['id']}/trash", json={"value": False})
    assert client.get(f"/certificates/{cert['id']}/download").status_code == 200


def test_profile_opt_in_does_not_expose_private_files(imported):
    client, _ = imported
    cert = client.get("/certificates").json()[0]
    body = {
        "enabled": False,
        "slug": "demo-person",
        "name": "Learner",
        "featured": [cert["id"]],
        "consent": True,
    }
    assert client.put("/profile", json=body).status_code == 200
    assert client.get("/public/demo-person").status_code == 404
    assert client.put("/profile", json={**body, "enabled": True}).status_code == 200
    public = client.get("/public/demo-person").json()
    assert len(public["certificates"]) == 1
    assert set(public["certificates"][0]) == {"title", "issuer", "category"}
    client.put(f"/certificates/{cert['id']}/trash", json={"value": True})
    assert client.get("/public/demo-person").json()["certificates"] == []
    client.put(f"/certificates/{cert['id']}/trash", json={"value": False})
    assert client.get("/public/demo-person").json()["certificates"] == []


def test_drafts_and_notification_reads(imported):
    client, _ = imported
    cert = client.get("/certificates").json()[0]
    draft = client.post(
        "/social-drafts", json={"certificate_id": cert["id"], "tone": "friendly"}
    ).json()
    assert draft["mode"] == "template"
    assert (
        client.patch(f"/social-drafts/{draft['id']}", json={"content": "My own words"}).status_code
        == 200
    )
    assert client.get("/social-drafts").json()[0]["content"] == "My own words"
    client.put("/notifications/read")
    assert all(n["read"] for n in client.get("/notifications").json())
    assert client.get("/export").headers["content-disposition"].startswith("attachment")


def test_settings_hard_cap_and_logout(client):
    assert client.put("/settings", json={"threshold_mib": 101, "name": "Demo"}).status_code == 422
    assert client.put("/settings", json={"threshold_mib": 1, "name": "Demo"}).status_code == 200
    assert client.get("/settings").json()["threshold_mib"] == 1
    assert (
        client.post(
            "/certificates/upload", files={"file": ("big.pdf", b" " * (1024 * 1024 + 1))}
        ).status_code
        == 422
    )
    client.delete("/auth/session")
    assert client.get("/certificates").status_code == 401


def test_request_limit_before_multipart_and_chunked_json(client):
    assert (
        client.post(
            "/certificates/upload", content=b"", headers={"Content-Length": str(101 * 1024 * 1024)}
        ).status_code
        == 413
    )
    response = client.put(
        "/settings",
        content=iter([b" " * 40000, b" " * 40000]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_search_includes_extracted_document_text_and_tags(client):
    data = sample_pdf("OnlyInsideDocument", "Source")
    key = client.post("/certificates/upload", files={"file": ("generic.pdf", data)}).json()["id"]
    assert len(client.get("/certificates?q=OnlyInsideDocument").json()) == 1
    client.patch(
        f"/certificates/{key}",
        json={"title": "Generic", "issuer": "Source", "category": "Other", "tags": ["needle-tag"]},
    )
    assert len(client.get("/certificates?q=needle-tag").json()) == 1
    assert client.get("/certificates?q=" + ("a" * 201)).status_code == 422
