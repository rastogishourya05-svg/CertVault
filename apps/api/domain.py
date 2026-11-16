"""Deterministic ingestion policy. No network access or AI decisions here."""

import hashlib
import ipaddress
from collections.abc import Iterable
from urllib.parse import urlsplit

MIB = 1024 * 1024
MB = 1_000_000
MAX_AUTO_THRESHOLD = 100 * MIB
HARD_CAP = 100 * MIB
STORAGE_HARD_CAP = 50 * MB


class PolicyError(ValueError):
    pass


class HardLimitExceeded(PolicyError):
    """Observed content crossed the non-approvable hard byte ceiling."""


def size_decision(
    size: int | None, threshold: int, approved: bool = False, *, hard_cap: int = HARD_CAP
) -> str:
    if not 1 <= threshold <= MAX_AUTO_THRESHOLD:
        raise PolicyError("Invalid download threshold")
    if size is not None and size < 0:
        return "rejected"
    if size is not None and size > hard_cap:
        return "rejected"
    if size is not None and size > threshold and not approved:
        return "awaiting_approval"
    return "eligible"


def bounded_bytes(
    chunks: Iterable[bytes],
    threshold: int,
    approved: bool = False,
    *,
    hard_cap: int = HARD_CAP,
) -> bytes:
    """Count observed bytes even if declared size lies; never retain partial results."""
    if not 1 <= threshold <= MAX_AUTO_THRESHOLD:
        raise PolicyError("Invalid download threshold")
    limit = hard_cap if approved else min(threshold, hard_cap)
    output = bytearray()
    for chunk in chunks:
        observed = len(output) + len(chunk)
        if observed > hard_cap:
            raise HardLimitExceeded("File exceeds the hard byte limit")
        if observed > limit:
            raise PolicyError("Observed file exceeds download limit; explicit approval required")
        output.extend(chunk)
    return bytes(output)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_url(url: str, allowed_hosts: set[str], resolved_ips: list[str]) -> None:
    """Preflight only. Production transport must pin these IPs and recheck every redirect."""
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise PolicyError("Only credential-free HTTPS on port 443 is supported")
    if p.hostname not in allowed_hosts or not resolved_ips:
        raise PolicyError("Link provider is not allowlisted")
    if any(
        not (address := ipaddress.ip_address(ip)).is_global
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for ip in resolved_ips
    ):
        raise PolicyError("Private or special-purpose address blocked")


def likely_certificate(subject: str, filename: str) -> bool:
    return filename.lower().endswith(".pdf") and any(
        word in (subject + " " + filename).lower()
        for word in ("certificate", "credential", "achievement")
    )
