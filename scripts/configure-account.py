"""Configure the isolated local Supabase account endpoint with hidden input."""

import base64
import getpass
import json

from cryptography.fernet import Fernet

from apps.api.account import AccountConfig
from apps.api.local_config import config_root, write_private

path = config_root() / "supabase-local.json"
if path.exists():
    raise SystemExit("Local account configuration already exists; preserving it.")
url = "http://127.0.0.1:54321"
key = getpass.getpass("Local Supabase anon/publishable key (input hidden): ").strip()
if len(key) < 32 or any(ch.isspace() for ch in key):
    raise SystemExit("Enter the local anon/publishable key from `supabase status`.")
if key.startswith("sb_secret_"):
    raise SystemExit("A project secret key is forbidden; use the local anon key only.")
if key.startswith("eyJ"):
    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        role = json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except (IndexError, ValueError, TypeError):
        role = None
    if role != "anon":
        raise SystemExit("The local key must have the anon role; service-role keys are forbidden.")
elif not key.startswith("sb_publishable_"):
    raise SystemExit("Use the local anon JWT or a Supabase publishable key.")
settings = AccountConfig(
    url=url, publishable_key=key, session_key=Fernet.generate_key().decode(), enabled=True
)
write_private(
    path,
    json.dumps(
        {
            "url": settings.url,
            "publishable_key": key,
            "session_key": settings.session_key.get_secret_value(),
            "enabled": True,
        }
    ),
)
print("Development account configured. Secrets were not printed; config is ignored by Git.")
