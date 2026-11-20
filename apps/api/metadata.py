"""Deterministic certificate metadata extraction from isolated PDF text."""

import re
from datetime import datetime

_FIELD = {
    "title": re.compile(
        r"^(?:course|program|credential|certificate title)\s*:\s*(.{2,160})$", re.I
    ),
    "issuer": re.compile(r"^(?:issuer|issued by|provided by|awarded by)\s*:\s*(.{2,120})$", re.I),
    "recipient": re.compile(
        r"^(?:awarded to|presented to|issued to|recipient|learner)\s*:\s*(.{2,120})$", re.I
    ),
    "date": re.compile(
        r"^(?:issue date|issued on|date issued|completion date)\s*:\s*(.{3,40})$", re.I
    ),
}
_DATE_FORMATS = (
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d %B %Y",
)


def extract_metadata(text: str, filename: str) -> dict:
    """Extract explicit labeled values only; preserve filename fallback provenance."""
    values = {}
    lines = [
        " ".join(line.split()).strip(" •·") for line in text.splitlines()[:500] if line.strip()
    ]
    for index, line in enumerate(lines):
        clean = " ".join(line.split()).strip(" \t•·")
        # OCR commonly places the label and its value on separate lines.
        if index + 1 < len(lines) and not any(
            pattern.fullmatch(clean) for pattern in _FIELD.values()
        ):
            candidate = lines[index + 1]
            if not any(
                pattern.match(candidate.rstrip(":") + ": value") or pattern.match(candidate)
                for pattern in _FIELD.values()
            ):
                combined = clean.rstrip(":") + ": " + candidate
                if any(pattern.fullmatch(combined) for pattern in _FIELD.values()):
                    clean = combined
        for field, pattern in _FIELD.items():
            match = pattern.match(clean)
            if match and field not in values:
                values[field] = match.group(1).strip(" \t.,;:")

    issued_on = None
    raw_date = values.get("date")
    if raw_date:
        for fmt in _DATE_FORMATS:
            try:
                issued_on = datetime.strptime(raw_date, fmt).date().isoformat()
                break
            except ValueError:
                continue

    title = values.get("title")
    title_source = "pdf_text" if title else "filename_review"
    if not title:
        title = (
            re.sub(r"(?i)\.(?:pdf|jpe?g|png)$", "", filename)
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )
    if not title:
        title = "Certificate needs review"

    searchable = (title + " " + text[:12000]).casefold()
    category = "Other"
    for label, words in (
        ("Technology", ("software", "programming", "python", "data", "cybersecurity", "cloud")),
        ("Business", ("leadership", "business", "management", "project manager")),
        ("Safety", ("safety", "first aid", "workplace")),
        ("Education", ("teaching", "education", "academic")),
    ):
        if any(re.search(r"\b" + re.escape(word) + r"\b", searchable) for word in words):
            category = label
            break

    provenance = {
        "title": title_source,
        "issuer": "pdf_text" if values.get("issuer") else "needs_review",
        "recipient": "pdf_text" if values.get("recipient") else "not_found",
        "issued_on": "pdf_text" if issued_on else "not_found",
        "category": "keyword_rule",
        "authenticity": "not_verified",
    }
    return {
        "title": title[:160],
        "issuer": values.get("issuer", "")[:120] or None,
        "recipient": values.get("recipient", "")[:120] or None,
        "issued_on": issued_on,
        "category": category,
        "provenance": provenance,
    }
