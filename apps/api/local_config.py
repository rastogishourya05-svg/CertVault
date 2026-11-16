"""Locations and permissions for ignored, server-only local configuration."""

import os
import secrets
import subprocess
from pathlib import Path


def config_root() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        return Path(appdata) / "CertVault"
    return Path.home() / ".config" / "certvault"


def _write_restricted(path: Path, data: str, *, exclusive: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        if os.name == "nt":
            user = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")
            result = subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{user}:(F)",
                    "SYSTEM:(F)",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                path.unlink(missing_ok=True)
                raise OSError("Could not restrict local configuration file permissions")
        else:
            os.chmod(path, 0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_private(path: Path, data: str) -> None:
    """Create a new config file with user-only access; never overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_restricted(path, data, exclusive=True)


def replace_private(path: Path, data: str) -> None:
    """Atomically replace a protected config without exposing its contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")
    try:
        _write_restricted(temporary, data, exclusive=True)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
