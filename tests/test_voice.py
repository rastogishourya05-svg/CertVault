import asyncio
import contextlib
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from apps.api import voice
from apps.api.account import gateway
from apps.api.main import app


@pytest.fixture
def service(client, monkeypatch):
    calls = []
    state = {"status": 200, "text": "Workplace safety", "count": 1}

    def handler(request):
        calls.append(request)
        return httpx.Response(state["status"], json={"text": state["text"]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    batch = MagicMock()

    async def execute():
        return [state["count"], True]

    batch.execute = execute
    auth = SimpleNamespace(
        identity=AsyncMock(return_value=("session", "owner", "private-token")),
        client=http,
        sessions=SimpleNamespace(pipeline=lambda **kwargs: contextlib.nullcontext(batch)),
    )
    app.dependency_overrides[gateway] = lambda: auth
    monkeypatch.setattr(voice, "api_key", lambda: "fixture-key")
    yield client, calls, state
    app.dependency_overrides.pop(gateway)
    asyncio.run(http.aclose())


headers = {
    "content-type": "application/octet-stream",
    "x-certvault-voice-consent": "send-recording",
}
path = "/account/voice/transcribe"


def test_transcription_sends_only_validated_audio(service):
    client, calls, _ = service
    data = b"\x00\x01" * 160
    res = client.post(path, headers=headers, content=data)
    assert res.json() == {"text": "Workplace safety"}
    request = calls[0]
    assert (
        request.url.host == "api.elevenlabs.io" and request.headers["xi-api-key"] == "fixture-key"
    )
    assert b"private-token" not in request.content and b"scribe_v2" in request.content
    with wave.open(
        io.BytesIO(request.content[request.content.index(b"RIFF") :]), "rb"
    ) as recording:
        assert recording.getframerate() == 16000 and recording.readframes(160) == data


def test_gate_consent_private_key_size_and_type(service, monkeypatch):
    client, calls, _ = service
    assert client.post(path, content=b"00").status_code == 400
    assert (
        client.post(
            path, headers={**headers, "content-type": "audio/mp4"}, content=b"00"
        ).status_code
        == 415
    )
    assert client.post(path, headers=headers, content=b"0").status_code == 422
    assert (
        client.post(path, headers=headers, content=b"x" * (voice.MAX_BYTES + 1)).status_code == 413
    )
    monkeypatch.setattr(voice, "api_key", lambda: "")
    assert client.get("/account/voice/status").json() == {"configured": False}
    assert client.post(path, headers=headers, content=b"00").status_code == 503
    assert not calls


def test_rate_limit_and_upstream_errors(service):
    client, calls, state = service
    state["count"] = 7
    assert client.post(path, headers=headers, content=b"00").status_code == 429
    assert not calls
    state.update(count=1, status=401)
    assert client.post(path, headers=headers, content=b"00").status_code == 503
    state.update(status=200, text="")
    assert client.post(path, headers=headers, content=b"00").status_code == 422


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (401, "quota_exceeded", "credit cap"),
        (401, "missing_permissions", "Enable Speech to Text"),
        (401, "invalid_api_key", "Save a valid key"),
        (403, None, "denied access"),
        (429, None, "Wait a minute"),
        (422, None, "new short recording"),
        (500, None, "Try later"),
    ],
)
def test_provider_errors_are_actionable_and_redacted(status, reason, expected):
    response = httpx.Response(
        status, json={"detail": {"status": reason, "message": "sensitive-provider-content"}}
    )
    message = voice.provider_error(response)
    assert expected in message and "sensitive-provider-content" not in message
