"""Certificate formats shared by ingestion, private storage and downloads."""

import hashlib
from pathlib import PurePath

FORMATS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def extension(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ValueError("Unsupported certificate format")


def matches(filename: str, data: bytes) -> bool:
    try:
        return FORMATS.get(PurePath(filename).suffix.lower()) == FORMATS[extension(data)]
    except ValueError:
        return False


def object_path(owner: str, data: bytes) -> str:
    return f"{owner}/{hashlib.sha256(data).hexdigest()}{extension(data)}"
