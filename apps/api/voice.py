"""Explicitly consented short dictation. Recordings and transcripts stay out of logs."""

import io
import os
import wave

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from redis.exceptions import RedisError

from apps.api.account import Gateway, gateway
from apps.api.local_config import config_root

router = APIRouter(prefix="/account/voice")
MAX_BYTES = 16_000 * 2 * 15


def api_key():
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    try:
        return (config_root() / "elevenlabs.key").read_text(encoding="utf8").strip()
    except OSError:
        return ""


@router.get("/status")
async def status(request: Request, g: Gateway = Depends(gateway)):
    await g.identity(request)
    return {"configured": bool(api_key())}


@router.post("/transcribe")
async def transcribe(request: Request, g: Gateway = Depends(gateway)):
    _, owner, _ = await g.identity(request)
    if request.headers.get("x-certvault-voice-consent") != "send-recording":
        raise HTTPException(400, "Confirm sending this recording to ElevenLabs.")
    if request.headers.get("content-type") != "application/octet-stream":
        raise HTTPException(415, "Unsupported recording format.")
    key = api_key()
    if not key:
        raise HTTPException(
            503, "Voice input needs an ElevenLabs key on the server. You can still type."
        )
    pcm = await request.body()
    if not 2 <= len(pcm) <= MAX_BYTES or len(pcm) % 2:
        raise HTTPException(422, "Record up to 15 seconds and try again.")
    rate_key = "cv:voice:" + owner
    try:
        async with g.sessions.pipeline(transaction=True) as batch:
            batch.incr(rate_key)
            batch.expire(rate_key, 60, nx=True)
            count, _ = await batch.execute()
    except RedisError:
        raise HTTPException(503, "Voice input temporarily unavailable.") from None
    if count > 6:
        raise HTTPException(429, "Please wait a minute before dictating again.")
    recording = io.BytesIO()
    with wave.open(recording, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    try:
        response = await g.client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key},
            files={"file": ("dictation.wav", recording.getvalue(), "audio/wav")},
            data={
                "model_id": "scribe_v2",
                "tag_audio_events": "false",
                "timestamps_granularity": "none",
            },
            timeout=25,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise HTTPException(
                503,
                "Transcription unavailable. Check the server key or ElevenLabs quota, or type instead.",
            )
        text = response.json().get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(422, "No speech recognized. Try again or type instead.")
        return {"text": text.strip()}
    except (httpx.RequestError, ValueError, AttributeError):
        raise HTTPException(
            502, "Could not transcribe the recording. You can still type."
        ) from None
