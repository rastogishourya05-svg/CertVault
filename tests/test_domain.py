import pytest

from apps.api.domain import (
    HARD_CAP,
    MB,
    MIB,
    STORAGE_HARD_CAP,
    PolicyError,
    bounded_bytes,
    likely_certificate,
    size_decision,
    validate_url,
)
from apps.api.processing import extract_pdf, sample_pdf


@pytest.mark.parametrize(
    ("size", "approved", "expected"),
    [
        (49 * MIB, False, "eligible"),
        (50 * MIB, False, "eligible"),
        (51 * MIB, False, "awaiting_approval"),
        (51 * MIB, True, "eligible"),
        (HARD_CAP + 1, True, "rejected"),
        (None, False, "eligible"),
        (-1, False, "rejected"),
    ],
)
def test_local_demo_size_boundaries(size, approved, expected):
    assert size_decision(size, 50 * MIB, approved) == expected


@pytest.mark.parametrize(
    ("size", "threshold", "approved", "expected"),
    [
        (49 * MB, 50 * MIB, False, "eligible"),
        (50 * MB, 50 * MIB, False, "eligible"),
        (50 * MB, 45 * MIB, False, "awaiting_approval"),
        (50 * MB, 45 * MIB, True, "eligible"),
        (50 * MIB, 100 * MIB, False, "rejected"),
        (51 * MB, 100 * MIB, False, "rejected"),
        (100 * MIB, 100 * MIB, True, "rejected"),
    ],
)
def test_supabase_free_storage_size_boundaries(size, threshold, approved, expected):
    assert size_decision(size, threshold, approved, hard_cap=STORAGE_HARD_CAP) == expected


def test_unknown_size_stream_stops_at_bound():
    yielded = []

    def stream():
        for _ in range(10):
            yielded.append(1)
            yield b"1234"

    with pytest.raises(PolicyError):
        bounded_bytes(stream(), 8)
    assert len(yielded) == 3
    assert bounded_bytes([b"1234", b"5678"], 8) == b"12345678"


def test_approved_stream_cannot_cross_storage_limit():
    from apps.api.domain import HardLimitExceeded

    with pytest.raises(HardLimitExceeded, match="hard byte limit"):
        bounded_bytes(
            [b"x" * (STORAGE_HARD_CAP + 1)],
            100 * MIB,
            approved=True,
            hard_cap=STORAGE_HARD_CAP,
        )


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.0.1", "224.0.0.1"]
)
def test_ssrf_private_addresses(ip):
    with pytest.raises(PolicyError):
        validate_url("https://issuer.example/cert", {"issuer.example"}, [ip])


@pytest.mark.parametrize(
    "url",
    [
        "http://issuer.example/a",
        "https://user:pass@issuer.example/a",
        "https://issuer.example:444/a",
        "https://evil.example/a",
    ],
)
def test_unsafe_urls(url):
    with pytest.raises(PolicyError):
        validate_url(url, {"issuer.example"}, ["8.8.8.8"])


def test_classifier_ignores_unrelated_mail():
    assert likely_certificate("Your certificate is ready", "award.pdf")
    assert likely_certificate("Your course is complete", "course-certificate.pdf")
    assert not likely_certificate("Certificate attached", "certificate.png")
    assert not likely_certificate("Your monthly statement", "statement.pdf")
    assert not likely_certificate("Certificate attached", "malware.exe")


def test_pdf_validation_and_no_invented_fields():
    text = extract_pdf(sample_pdf("Cloud Foundations", "Sample School"))
    assert "Cloud Foundations" in text
    assert "Synthetic sample" in text
    with pytest.raises(PolicyError):
        extract_pdf(b"not a pdf")


def test_malformed_pdf_rejected():
    with pytest.raises(PolicyError):
        extract_pdf(b"%PDF-1.7 broken")
