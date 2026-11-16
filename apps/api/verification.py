"""Issuer links are evidence references, never proof of authenticity by themselves."""

import re
from urllib.parse import urlsplit, urlunsplit

_ISSUERS = {
    "coursera.org": (
        "Coursera",
        r"/verify/(?:professional-cert/|specialization/)?[A-Za-z0-9-]{6,100}/?",
    ),
    "www.coursera.org": (
        "Coursera",
        r"/verify/(?:professional-cert/|specialization/)?[A-Za-z0-9-]{6,100}/?",
    ),
    "www.udemy.com": ("Udemy", r"/certificate/UC-[A-Za-z0-9-]{8,100}/?"),
    "www.credly.com": ("Credly", r"/badges/[A-Za-z0-9-]{8,100}(?:/public_url)?/?"),
}


def verification_details(text: str) -> dict:
    match = re.search(
        r"(?:credential|certificate|verification)\s*(?:id|number|no\.?|code)\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9./_-]{3,119})",
        text[:50000],
        re.I,
    )
    links = []
    for raw in re.findall(r"https://[^\s<>\"']{1,1000}", text[:50000]):
        raw = raw.rstrip(".,;:)")
        try:
            p = urlsplit(raw)
            if p.username or p.password or p.port not in (None, 443):
                continue
            issuer, pattern = _ISSUERS.get(p.hostname, (None, None))
            if not issuer or not re.fullmatch(pattern, p.path):
                continue
            url = urlunsplit(("https", p.hostname, p.path, "", ""))
            if not any(link["url"] == url for link in links):
                links.append({"issuer": issuer, "url": url})
        except ValueError:
            continue
    return {
        "credential_id": match.group(1) if match else None,
        "issuer_links": links[:5],
        "status": "issuer_review_available" if links else "unverified",
        "explanation": "Compare recipient, course, date and credential ID on the issuer's page. "
        "A URL, OCR result or downloaded PDF alone does not prove authenticity.",
    }
