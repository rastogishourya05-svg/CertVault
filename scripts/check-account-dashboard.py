"""Exercise local Auth, PostgREST and RLS with two short-lived synthetic accounts."""

import argparse
import json
import os
import secrets
import subprocess
import uuid
from contextlib import ExitStack
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.account import config
from apps.api.local_config import config_root, write_private
from apps.api.main import app
from apps.api.processing import sample_pdf


def fixture_sql(statement):
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "supabase_db_CertVault",
            "psql",
            "-X",
            "-q",
            "-1",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
        ],
        input=statement,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def remove_fixture_pdf(owner, data):
    # The local Storage service performs its own object deletion. Its internal
    # credential stays in that container and is never exported to the app or host.
    from apps.api.documents import object_path

    key = object_path(str(uuid.UUID(str(owner))), data)
    script = r"""
      const path = process.argv[1];
      if (!/^[a-f0-9-]{36}\/[a-f0-9]{64}\.(pdf|png|jpg)$/.test(path)) process.exit(2);
      fetch("http://127.0.0.1:5000/object/certificates/" + path, {
        method: "DELETE", headers: {Authorization: "Bearer " + process.env.SERVICE_KEY}
      }).then(r => {if (!r.ok && r.status !== 404) throw Error("Fixture cleanup HTTP "+r.status)});
    """
    subprocess.run(
        ["docker", "exec", "supabase_storage_CertVault", "node", "-e", script, key], check=True
    )


def check(browser):
    settings = config()
    if not settings or settings.url != "http://127.0.0.1:54321":
        raise RuntimeError("Local Supabase configuration required.")
    with ExitStack() as stack:
        owners = []
        users = []
        accounts = []
        for label in "AB":
            client = stack.enter_context(TestClient(app))
            email = f"dashboard-{uuid.uuid4().hex}@example.test"
            password = secrets.token_urlsafe(32)
            response = client.post("/account/register", json={"email": email, "password": password})
            assert response.status_code == 201, response.status_code
            owner = uuid.UUID(response.json()["id"])
            owners.append(owner)
            stack.callback(
                fixture_sql, f"delete from auth.users where id='{owner}' and email='{email}'"
            )
            assert client.post("/account/logout").is_success
            assert client.post(
                "/account/login", json={"email": email, "password": password}
            ).is_success
            title = f"Synthetic dashboard credential {label}"
            pdf = sample_pdf(f"Course: {title}", "Fixture Academy")
            file = {"file": (f"{title}.pdf", pdf, "application/pdf")}
            upload = client.post("/account/certificates/upload", files=file)
            assert upload.status_code == 200, upload.status_code
            stack.callback(remove_fixture_pdf, owner, pdf)
            cert = uuid.UUID(upload.json()["certificate_id"])
            assert upload.json()["status"] == "stored"
            assert (
                client.post("/account/certificates/upload", files=file).json()["status"]
                == "duplicate"
            )
            download = f"/account/pipeline/certificates/{cert}/download"
            assert client.get(download).content == pdf
            assert client.get(download + "?inline=true").content == pdf
            assert client.put(
                "/account/profile",
                json={
                    "display_name": f"Synthetic learner {label}",
                    "download_limit_bytes": 50000000,
                },
            ).is_success
            accounts.append({"email": email, "password": password, "title": title})
            users.append((client, cert))
        (first, cert), (other, other_cert) = users
        assert first.get("/account/certificates").json()[0]["id"] == str(cert)
        assert [r["id"] for r in other.get("/account/certificates").json()] == [str(other_cert)]
        assert other.get(f"/account/pipeline/certificates/{cert}/download").status_code == 404
        for kind, relation in [("collections", "collection_items"), ("tags", "certificate_tags")]:
            base = f"/account/organization/{kind}"
            created = first.post(base, json={"name": "Dashboard fixture"})
            assert created.status_code == 201, created.status_code
            group = created.json()[0]["id"]
            membership = f"{base}/{group}/{cert}"
            assert first.put(membership).is_success
            assert first.put(membership).is_success
            assert first.get(base).json()[0][relation] == [{"certificate_id": str(cert)}]
            assert other.get(base).json() == []
            assert not other.put(membership).is_success
            assert other.delete(membership).is_success
            assert first.get(base).json()[0][relation] == [{"certificate_id": str(cert)}]
            assert first.delete(membership).is_success
            assert first.get(base).json()[0][relation] == []
        assert first.get("/account/pipeline/status").is_success
        review = {
            "title": "Reviewed fixture",
            "issuer": "Example academy",
            "recipient": "Syntheticname",
            "category": "Training",
        }
        route = f"/account/certificates/{cert}/review"
        assert other.put(route, json=review).status_code == 404
        assert first.put(route, json=review).is_success
        assert [row["id"] for row in first.get("/account/certificates?q=Syntheticname").json()] == [
            str(cert)
        ]
        change = {"operation": "trash", "ids": [str(cert)]}
        assert other.post("/account/vault/bulk", json=change).json()["updated"] == 0
        assert first.post("/account/vault/bulk", json=change).json()["updated"] == 1
        assert first.get("/account/certificates").json() == []
        assert first.get("/account/certificates?trash=true").json()[0]["reviewed_at"]
        assert first.get(f"/account/pipeline/certificates/{cert}/download").status_code == 404
        assert (
            first.post("/account/vault/bulk", json={**change, "operation": "restore"}).json()[
                "updated"
            ]
            == 1
        )
        import io
        import zipfile

        archive = first.post("/account/pipeline/export", json={})
        assert archive.is_success, archive.status_code
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            rows = json.loads(bundle.read("certificates.json"))
            assert [r["id"] for r in rows] == [str(cert)]
            assert (
                bundle.read(rows[0]["file"])
                == first.get(f"/account/pipeline/certificates/{cert}/download").content
            )
        assert first.put(route, json={**review, "title": accounts[0]["title"]}).is_success
        if browser:
            fixture = config_root() / f"dashboard-check-{uuid.uuid4().hex}.json"
            write_private(fixture, json.dumps({"accounts": accounts}))
            stack.callback(fixture.unlink, missing_ok=True)
            env = {
                **os.environ,
                "CERTVAULT_ACCOUNT_FIXTURE": str(fixture),
                "CERTVAULT_LIVE_TESTS": "1",
                "PLAYWRIGHT_CHANNEL": "chrome",
            }
            subprocess.run(
                [
                    "node",
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    "account-live.spec.ts",
                    "--trace",
                    "off",
                ],
                env=env,
                cwd=Path(__file__).resolve().parents[1] / "apps/web",
                check=True,
            )
        import pymupdf

        with pymupdf.open(stream=pdf, filetype="pdf") as source:
            for fmt, mime in [("png", "image/png"), ("jpeg", "image/jpeg")]:
                data = source[0].get_pixmap(dpi=150).tobytes(fmt)
                files = {"file": ("Certificate." + fmt, data, mime)}
                upload = first.post("/account/certificates/upload", files=files)
                assert upload.status_code == 200, upload.status_code
                stack.callback(remove_fixture_pdf, owners[0], data)
                assert upload.json()["status"] == "stored"
                assert (
                    first.post("/account/certificates/upload", files=files).json()["status"]
                    == "duplicate"
                )
                route = (
                    "/account/pipeline/certificates/"
                    + upload.json()["certificate_id"]
                    + "/download"
                )
                download = first.get(route)
                assert download.content == data and download.headers["content-type"] == mime
                assert other.get(route).status_code == 404
        import html
        import re
        import time
        from urllib.parse import parse_qs, urlsplit

        import httpx

        email = accounts[0]["email"]
        assert first.post("/account/recovery/request", json={"email": email}).is_success
        with httpx.Client(base_url="http://127.0.0.1:54324", trust_env=False) as mail:
            for _ in range(20):
                matches = (
                    mail.get("/api/v1/search", params={"query": "to:" + email})
                    .raise_for_status()
                    .json()["messages"]
                )
                if matches:
                    break
                time.sleep(0.25)
            msg = next(
                m
                for m in matches
                if any(t["Address"] == email for t in m["To"])
                and "password" in m["Subject"].lower()
            )
            body = mail.get("/api/v1/message/" + msg["ID"]).raise_for_status().json()["HTML"]
            urls = [
                parse_qs(urlsplit(html.unescape(u)).query)
                for u in re.findall(r'href="([^"]+)"', body)
            ]
            proof = next(q["token"][0] for q in urls if q.get("type") == ["recovery"])
            password = secrets.token_urlsafe(32)
            payload = {"password": password, "token_hash": proof}
            reset = first.post("/account/recovery/finish", json=payload)
            assert reset.is_success, reset.status_code
            assert first.get("/account/certificates").status_code == 401
            assert not first.post("/account/recovery/finish", json=payload).is_success
            assert not first.post(
                "/account/login", json={"email": email, "password": accounts[0]["password"]}
            ).is_success
            assert first.post(
                "/account/login", json={"email": email, "password": password}
            ).is_success
            mail.request("DELETE", "/api/v1/messages", json={"IDs": [msg["ID"]]}).raise_for_status()
        for client, _ in users:
            assert client.post("/account/logout").is_success
    print(
        "Local registration, sign-in, private PDF upload, duplicate handling, download, collections, tags, isolation, status, logout and fixture cleanup passed."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    check(parser.parse_args().browser)
