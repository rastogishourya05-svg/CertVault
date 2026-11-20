from getpass import getpass

from apps.api.local_config import config_root, replace_private

if __name__ == "__main__":
    key = getpass("ElevenLabs speech-to-text API key (hidden): ").strip()
    if not key:
        raise SystemExit("No key entered.")
    replace_private(config_root() / "elevenlabs.key", key)
    print("Saved private server configuration. No provider request was made.")
