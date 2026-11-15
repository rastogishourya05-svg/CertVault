"""Interactive secret input; never echoes credentials or enables live mailbox scanning."""

import getpass
import json
from pathlib import Path

from cryptography.fernet import Fernet

from apps.api.pipeline_config import PipelineConfig

path = Path(".local/pipeline.json")
if path.exists():
    raise SystemExit("Configuration already exists; preserve encryption keys. No changes made.")
config = PipelineConfig(
    database_url=getpass.getpass("Backend PostgreSQL URL (TLS verified outside loopback): "),
    storage_key=getpass.getpass("Server-only Supabase Storage secret: "),
    google_client_id=input("Google Web OAuth client ID: ").strip(),
    google_client_secret=getpass.getpass("Google OAuth client secret: "),
    oauth_key=Fernet.generate_key().decode(),
    live_imports_enabled=False,
)
# model_dump_json deliberately masks SecretStr; explicitly serialize only to ignored config.
data = config.model_dump()
for key in ("database_url", "storage_key", "oauth_key", "google_client_secret"):
    data[key] = getattr(config, key).get_secret_value()
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("Saved ignored server configuration. Live imports remain DISABLED. Do not share this file.")
