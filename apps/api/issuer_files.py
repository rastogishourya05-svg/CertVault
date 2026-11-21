"""Direct issuer-file imports. Never forward Gmail credentials or follow redirects."""

import base64
import hashlib
import html
import http.client
import re
import socket
import ssl
import time
from urllib.parse import parse_qsl, urlsplit

from apps.api.domain import STORAGE_HARD_CAP, HardLimitExceeded, PolicyError, validate_url

HOST = "udemy-certificate.s3.amazonaws.com"
FILE = re.compile(
    r"/(?:pdf/UC-[a-zA-Z0-9-]{4,100}\.pdf|image/UC-[a-zA-Z0-9-]{4,100}\.jpe?g)\Z", re.I
)
URL = re.compile(r"""https://[^\s<>"']{1,2048}""", re.I)


def target(url):
    p = urlsplit(url)
    if (
        p.netloc.lower() != HOST
        or p.scheme != "https"
        or p.query
        or p.fragment
        or not FILE.fullmatch(p.path)
    ):
        raise ValueError("Unsupported issuer link")
    return p.path


def credly_badge(url):
    # Forwarders sometimes put the real destination inside a tracking URL.
    # Inspect the text locally and rebuild only an exact Credly badge address.
    try:
        destinations = [url] + [
            value
            for key, value in parse_qsl(urlsplit(url).query, max_num_fields=32)
            if key.lower() in {"url", "target", "redirect", "destination", "q"}
        ]
    except ValueError:
        destinations = [url]
    for destination in destinations:
        badge = re.fullmatch(
            r"https://(?:www\.)?credly\.com/badges/([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?:/public_url)?/?(?:[?#][^\s]*)?",
            destination,
            re.I,
        )
        if badge:
            return badge
    return None


def message_links(payload, subject):
    """Keep only source fingerprints; reread the message to resolve approved links."""
    pending = [payload]
    found = {}
    invitation = False
    for _ in range(200):
        if not pending or len(found) >= 12:
            break
        part = pending.pop()
        pending.extend(part.get("parts", [])[:200])
        if part.get("mimeType") not in ("text/plain", "text/html"):
            continue
        raw = part.get("body", {}).get("data", "")
        if not isinstance(raw, str) or len(raw) > 256000:
            continue
        try:
            body = html.unescape(base64.urlsafe_b64decode(raw + "==").decode("utf8", "replace"))
        except ValueError:
            continue
        # Forwarded invitations often contain an opaque acceptance button.
        visible = re.sub(r"<[^>]{1,2048}>", " ", body)
        words = " ".join((subject + " " + visible).lower().split())
        if "credly" in (subject + body).lower() and re.search(
            r"\b(?:(?:accept|claim|view) (?:your|this) (?:digital )?badge|"
            r"you(?: have|'ve|\u2019ve) (?:earned|received) (?:a |an |the |your )?[^.!?]{0,80}badge)\b",
            words,
        ):
            invitation = True
        for match in URL.finditer(body):
            if len(found) >= 12:
                break
            url = match.group().rstrip(".,;:)")
            try:
                path = target(url)
                filename = path.rsplit("/", 1)[1]
            except ValueError:
                badge = credly_badge(url)
                if badge:
                    badge_id = badge[1].lower()
                    found["credly:" + badge_id] = (
                        "Credly badge",
                        "https://www.credly.com/badges/" + badge_id,
                    )
                    continue
                credential = re.fullmatch(
                    r"https://(?:www\.)?coursera\.org/verify/(?:professional-cert/|specialization/)?([A-Za-z0-9]{10,32})/?(?:[?#][^\s]*)?",
                    url,
                )
                provider = "Coursera"
                if not credential:
                    provider = "Udemy"
                    credential = re.fullmatch(
                        r"https://www\.udemy\.com/certificate/(UC-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})/?(?:[?#][^\s]*)?",
                        url,
                    )
                if credential:
                    canonical = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
                    key = "link:credential:" + canonical
                    found[key] = (provider + " credential " + credential[1], canonical)
                continue
            key = "link:" + hashlib.sha256(url.encode()).hexdigest()
            found[key] = (filename, url)
            if len(found) >= 12:
                break
    if invitation and not any(key.startswith("credly:") for key in found):
        found["link:credly-invitation"] = ("Credly badge invitation", "")
    return found


class LinkUnavailable(ValueError):
    pass


def fetch_file(url):
    path = target(url)
    deadline = time.monotonic() + 25
    try:
        candidates = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        validate_url(url, {HOST}, [entry[4][0] for entry in candidates])
        family, kind, proto, _, peer = candidates[0]
        context = ssl.create_default_context()
        with socket.socket(family, kind, proto) as raw:
            raw.settimeout(6)
            raw.connect(peer)
            with context.wrap_socket(raw, server_hostname=HOST) as tls:
                tls.sendall(
                    f"GET {path} HTTP/1.1\r\nHost: {HOST}\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n".encode(
                        "ascii"
                    )
                )
                with http.client.HTTPResponse(tls) as response:
                    response.begin()
                    if (
                        response.status != 200
                        or response.getheader("Content-Encoding", "identity").lower() != "identity"
                    ):
                        raise LinkUnavailable()
                    size = response.getheader("Content-Length")
                    if (
                        not size
                        or not re.fullmatch(r"[0-9]{1,18}", size)
                        or response.getheader("Transfer-Encoding")
                    ):
                        raise LinkUnavailable()
                    if int(size) > STORAGE_HARD_CAP:
                        raise HardLimitExceeded()
                    body = bytearray()
                    while time.monotonic() < deadline:
                        chunk = response.read1(min(65536, STORAGE_HARD_CAP - len(body) + 1))
                        if not chunk:
                            if size and len(body) != int(size):
                                raise LinkUnavailable()
                            return bytes(body)
                        body.extend(chunk)
                        if len(body) > STORAGE_HARD_CAP:
                            raise HardLimitExceeded()
                    raise LinkUnavailable()
    except HardLimitExceeded:
        raise
    except (OSError, ValueError, http.client.HTTPException, PolicyError) as exc:
        raise LinkUnavailable() from exc
