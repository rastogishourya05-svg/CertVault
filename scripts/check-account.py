"""Real BFF/Auth/RLS test against approved temporary accounts. No secret output."""

import json
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from redis import Redis

fixture = json.loads(Path(".local/account-test.json").read_text(encoding="utf-8"))
config = json.loads(Path(".local/supabase.json").read_text(encoding="utf-8"))
sessions = Redis.from_url("redis://127.0.0.1:6379/0", socket_timeout=5)
cipher = Fernet(config["session_key"].encode())
checks = {}


def require(response, status=200):
    if response.status_code != status:
        raise RuntimeError(
            f"Account integration response {response.status_code}; expected {status}. No credentials logged."
        )
    return response


with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
    for index, account in enumerate(fixture["accounts"]):
        login = require(
            client.post(
                "/account/login", json={"email": account["email"], "password": account["password"]}
            )
        )
        assert login.json()["id"] == account["id"]
        assert "access_token" not in login.text and "refresh_token" not in login.text
        assert "HttpOnly" in login.headers["set-cookie"]
        certs = require(client.get("/account/certificates")).json()
        assert [c["id"] for c in certs] == [account["certificate_id"]]
        other = fixture["accounts"][1 - index]
        require(
            client.patch(
                "/account/certificates/" + other["certificate_id"],
                json={
                    "title": "Cannot change another owner",
                    "issuer": "Fixture",
                    "favorite": True,
                },
            ),
            404,
        )
        require(
            client.patch(
                "/account/certificates/" + account["certificate_id"],
                json={
                    "title": f"Synthetic hosted credential {'AB'[index]}",
                    "issuer": "Integration fixture",
                    "favorite": True,
                },
            )
        )
        profile = {
            "display_name": f"Synthetic learner {'AB'[index]}",
            "download_limit_bytes": 1048576,
        }
        require(client.put("/account/profile", json=profile))
        assert require(client.get("/account/profile")).json() == profile
        sid = client.cookies.get("cv_account")
        key = "cv:session:" + sid
        stored = sessions.get(key)
        assert stored and b"access_token" not in stored
        record = json.loads(cipher.decrypt(stored))
        record["expires_at"] = time.time() - 1
        sessions.setex(key, 3600, cipher.encrypt(json.dumps(record).encode()))
        assert require(client.get("/account/status")).json()["authenticated"]
        assert json.loads(cipher.decrypt(sessions.get(key)))["expires_at"] > time.time()
        record = json.loads(cipher.decrypt(sessions.get(key)))
        # An authenticated client must not bypass the server-side scanner by uploading directly.
        denied = httpx.post(
            config["url"]
            + "/storage/v1/object/certificates/"
            + account["id"]
            + "/forbidden-test.pdf",
            headers={
                "apikey": config["publishable_key"],
                "Authorization": "Bearer " + record["access_token"],
                "Content-Type": "application/pdf",
            },
            content=b"%PDF-1.7 synthetic forbidden upload",
            timeout=20,
        )
        assert denied.status_code in (400, 401, 403)
        denial = denied.json()
        assert (
            str(denial.get("statusCode")) == "403"
            and "row-level security" in denial.get("message", "").lower()
        )
        assert require(client.post("/account/logout")).json()["provider_revocation_confirmed"]
        assert not sessions.get(key)
        client.cookies.set("cv_account", sid)
        assert not require(client.get("/account/status")).json()["authenticated"]
        client.cookies.clear()
checks.update(
    sign_in="passed",
    opaque_http_only_sessions="passed",
    encrypted_redis="passed",
    cross_user_isolation="passed",
    profile_write="passed",
    refresh="passed",
    direct_storage_upload_denied="passed",
    sign_out_and_replay_denial="passed",
)
Path("docs/evidence/account-integration.json").write_text(
    json.dumps(checks, indent=2) + "\n", encoding="utf-8"
)
print("Real Supabase account integration: all eight checks passed for both temporary accounts")
