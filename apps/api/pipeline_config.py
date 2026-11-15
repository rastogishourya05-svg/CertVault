"""Server-only pipeline configuration. Reading config never enables mailbox access."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from apps.api.providers import OAuthConfig, TokenCipher


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database_url: SecretStr
    storage_key: SecretStr
    oauth_key: SecretStr
    google_client_id: str
    google_client_secret: SecretStr
    redirect_uri: str = "http://127.0.0.1:8000/account/pipeline/gmail/callback"
    # Explicit security-sensitive activation, independent of the demo mode.
    live_imports_enabled: bool = False
    clamd_host: str = "127.0.0.1"
    clamd_port: int = Field(default=3310, ge=1, le=65535)
    parser_image: str = Field(default="certvault-parser:dev", pattern=r"^[a-zA-Z0-9./:_@-]+$")

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
    path = Path(os.getenv("CERTVAULT_PIPELINE_CONFIG", ".local/pipeline.json"))
    if not path.exists():
        return None
    return PipelineConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
