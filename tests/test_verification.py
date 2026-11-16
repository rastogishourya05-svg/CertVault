from apps.api.verification import verification_details


def test_issuer_reference_is_not_authenticity_proof():
    result = verification_details(
        "Credential ID: ABC-12345\nhttps://www.coursera.org/verify/ABC12345?tracking=secret"
    )
    assert result["credential_id"] == "ABC-12345"
    assert result["status"] == "issuer_review_available"
    assert result["issuer_links"][0]["url"] == "https://www.coursera.org/verify/ABC12345"


def test_untrusted_links_never_become_verification_links():
    for url in [
        "https://www.coursera.org.evil.test/verify/ABC12345",
        "http://www.coursera.org/verify/ABC12345",
        "https://127.0.0.1/verify/ABC12345",
        "https://user:pass@www.coursera.org/verify/ABC12345",
        "https://www.coursera.org:8443/verify/ABC12345",
        "https://www.coursera.org/redirect/ABC12345",
    ]:
        assert verification_details(url)["issuer_links"] == []
