"""Server-only pipeline configuration. Reading config never enables mailbox access."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from apps.api.local_config import config_root
from apps.api.providers import OAuthConfig, TokenCipher


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database_url: SecretStr
    oauth_key: SecretStr
    google_client_id: str
    google_client_secret: SecretStr
    redirect_uri: str = "http://127.0.0.1:8000/account/pipeline/gmail/callback"
    # Explicit security-sensitive activation, independent of the demo mode.
    live_imports_enabled: bool = False
    clamd_host: str = "127.0.0.1"
    clamd_port: int = Field(default=3310, ge=1, le=65535)
    parser_image: str = Field(default="certvault-parser:dev", pattern=r"^[a-zA-Z0-9./:_@-]+$")

    @field_validator("database_url")
    @classmethod
    def local_database_only(cls, value):
        url = urlsplit(value.get_secret_value())
        if url.scheme not in ("postgres", "postgresql") or url.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise ValueError("Hackathon MVP pipeline database must be local loopback Supabase")
        return value

    @field_validator("oauth_key")
    @classmethod
    def encryption_key(cls, value):
        TokenCipher(value.get_secret_value())
        return value

    @field_validator("redirect_uri")
    @classmethod
    def callback(cls, value):
        # Deliberately a single loopback callback; no external tunnels or open redirects.
        if value != "http://127.0.0.1:8000/account/pipeline/gmail/callback":
            raise ValueError("Only the configured loopback development callback is supported")
        return value

    def oauth(self):
        return OAuthConfig(
            "gmail", self.google_client_id, self.google_client_secret, self.redirect_uri
        )


def load_pipeline() -> PipelineConfig | None:
    path = Path(os.getenv("CERTVAULT_PIPELINE_CONFIG", str(config_root() / "pipeline.json")))
    if not path.exists():
        return None
    return PipelineConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
