from fastapi.testclient import TestClient

from apps.api.scan_review import service

client = TestClient(service)


def test_missing_answer_uses_recorded_evidence():
    result = client.post(
        "/explain",
        json={
            "intent": "missing",
            "counts": {"needs_review": 1},
            "completed": True,
            "document_review": True,
        },
    )
    assert result.status_code == 200
    assert "OCR" in result.json()["answer"]


def test_private_and_unknown_fields_are_refused():
    assert (
        client.post(
            "/explain",
            json={"intent": "summary", "counts": {}, "completed": True, "email": "private"},
        ).status_code
        == 422
    )


def test_historical_counts_are_unknown():
    assert (
        "historical"
        in client.post(
            "/explain", json={"intent": "summary", "counts": None, "completed": True}
        ).json()["answer"]
    )
