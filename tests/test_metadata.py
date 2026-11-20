from apps.api.metadata import extract_metadata


def test_labeled_certificate_metadata_is_extracted_with_field_provenance():
    result = extract_metadata(
        """CERTIFICATE OF COMPLETION
Course: Workplace Safety Basics
Awarded to: Demo User
Issuer: Example Training Institute
Issue date: November 16, 2026
""",
        "demo-certificate.pdf",
    )
    assert result == {
        "title": "Workplace Safety Basics",
        "issuer": "Example Training Institute",
        "recipient": "Demo User",
        "issued_on": "2026-11-16",
        "category": "Safety",
        "provenance": {
            "title": "pdf_text",
            "issuer": "pdf_text",
            "recipient": "pdf_text",
            "issued_on": "pdf_text",
            "category": "keyword_rule",
            "authenticity": "not_verified",
        },
    }


def test_unlabeled_metadata_is_not_invented_and_filename_needs_review():
    result = extract_metadata("Certificate of completion", "cloud-fundamentals.pdf")
    assert result["title"] == "cloud fundamentals"
    assert result["issuer"] is None
    assert result["recipient"] is None
    assert result["issued_on"] is None
    assert result["provenance"]["title"] == "filename_review"


def test_stacked_ocr_labels_and_missing_values():
    result = extract_metadata(
        "Course:\nCloud fundamentals\nIssued to\nExample learner\nIssuer:\nIssue date: 2026-11-20",
        "certificate.jpg",
    )
    assert result["title"] == "Cloud fundamentals"
    assert result["recipient"] == "Example learner"
    assert result["issuer"] is None
    assert result["issued_on"] == "2026-11-20"
