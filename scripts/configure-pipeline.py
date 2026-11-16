"""Configure local Gmail/Pipeline secrets without command-line or chat exposure."""

import getpass
import json
from urllib.parse import quote

from cryptography.fernet import Fernet

from apps.api.local_config import config_root, write_private
from apps.api.pipeline_config import PipelineConfig

path = config_root() / "pipeline.json"
if path.exists():
    raise SystemExit("Pipeline configuration already exists; preserving it.")

client_id = input("Google OAuth Web client ID: ").strip()
if not client_id.endswith(".apps.googleusercontent.com"):
    raise SystemExit("Enter the Web application client ID from Google Cloud.")
client_secret = getpass.getpass("Google OAuth client secret (input hidden): ").strip()
if not client_secret:
    raise SystemExit("Client secret is required; no configuration was written.")

db_password = getpass.getpass("LOCAL certvault_ingest PostgreSQL password (input hidden): ")
if not db_password:
    raise SystemExit("Local ingestion-role password is required; no configuration was written.")
database_url = (
    "postgresql://certvault_ingest:" + quote(db_password, safe="") + "@127.0.0.1:54322/postgres"
)

activation_phrase = "ENABLE MANUAL GMAIL IMPORTS"
print(
    "Live Gmail is disabled by default. Only continue after confirming this is the "
    "dedicated test mailbox and the local Storage ticket migration passed."
)
enable_live = (
    input(
        f"Type {activation_phrase!r} to arm manual Gmail scans, or press Enter to keep them off: "
    )
    == activation_phrase
)

settings = PipelineConfig(
    database_url=database_url,
    oauth_key=Fernet.generate_key().decode(),
    google_client_id=client_id,
    google_client_secret=client_secret,
    live_imports_enabled=enable_live,
)
write_private(
    path,
    json.dumps(
        {
            "database_url": settings.database_url.get_secret_value(),
            "oauth_key": settings.oauth_key.get_secret_value(),
            "google_client_id": settings.google_client_id,
            "google_client_secret": settings.google_client_secret.get_secret_value(),
            "redirect_uri": settings.redirect_uri,
            "live_imports_enabled": enable_live,
            "clamd_host": settings.clamd_host,
            "clamd_port": settings.clamd_port,
            "parser_image": settings.parser_image,
        }
    ),
)
print(
    "Local pipeline configuration saved. "
    + (
        "Manual Gmail imports are enabled."
        if enable_live
        else "Live Gmail imports remain disabled."
    )
)
