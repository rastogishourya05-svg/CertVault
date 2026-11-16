"""Switch the existing local pipeline config to the restricted ingest login."""

import getpass
import json
import os
from pathlib import Path
from urllib.parse import quote

from apps.api.local_config import config_root, replace_private
from apps.api.pipeline_config import PipelineConfig
from apps.api.postgres import connect

path = Path(os.getenv("CERTVAULT_PIPELINE_CONFIG", str(config_root() / "pipeline.json")))
current = PipelineConfig.model_validate_json(path.read_text(encoding="utf-8"))
password = getpass.getpass("LOCAL certvault_ingest PostgreSQL password (input hidden): ")
if not password:
    raise SystemExit("Password is required; the existing config was left unchanged.")

database_url = (
    "postgresql://certvault_ingest:" + quote(password, safe="") + "@127.0.0.1:54322/postgres"
)

try:
    with connect(database_url) as db:
        db.execute("set role certvault_pipeline")
        roles = db.execute("select session_user,current_user").fetchone()
        if roles != {
            "session_user": "certvault_ingest",
            "current_user": "certvault_pipeline",
        }:
            raise ValueError("Unexpected database roles")
except Exception:
    raise SystemExit(
        "The local restricted database login could not SET ROLE certvault_pipeline. "
        "Check its password and local role grant; the existing config was left unchanged."
    ) from None

updated = {
    "database_url": database_url,
    "oauth_key": current.oauth_key.get_secret_value(),
    "google_client_id": current.google_client_id,
    "google_client_secret": current.google_client_secret.get_secret_value(),
    "redirect_uri": current.redirect_uri,
    "live_imports_enabled": current.live_imports_enabled,
    "clamd_host": current.clamd_host,
    "clamd_port": current.clamd_port,
    "parser_image": current.parser_image,
}
PipelineConfig.model_validate(updated)
replace_private(path, json.dumps(updated))
print("Local pipeline database login verified and config updated; credentials were not displayed.")
