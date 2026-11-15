"""Write ignored development account config from environment, without printing secrets."""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

from apps.api.account import AccountConfig

path = Path(".local/supabase.json")
if path.exists():
    raise SystemExit("Configuration already exists; preserving the current session encryption key")
url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
if not url or not key.startswith("sb_publishable_"):
    raise SystemExit("Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in the environment first")
settings = AccountConfig(
    url=url, publishable_key=key, session_key=Fernet.generate_key().decode(), enabled=True
)
path.parent.mkdir(exist_ok=True)
path.write_text(
    json.dumps(
        {
            "url": settings.url,
            "publishable_key": key,
            "session_key": settings.session_key.get_secret_value(),
            "enabled": True,
        }
    ),
    encoding="utf-8",
)
print("Development account configured. Secrets were not printed; config is ignored by Git.")
