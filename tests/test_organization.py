from fastapi.testclient import TestClient

from apps.api.main import app


def test_tags_collections_and_bulk_actions_are_owner_scoped(imported):
    client, _ = imported
    cert = client.get("/certificates").json()[0]
    edited = client.patch(
        f"/certificates/{cert['id']}",
        json={
            "title": cert["title"],
            "issuer": cert["issuer"],
            "category": "Other",
            "tags": [" Cloud ", "cloud", "Growth"],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["tags"] == ["cloud", "growth"]
    created = client.post(
        "/collections", json={"name": "Next chapter", "certificate_ids": [cert["id"]]}
    ).json()
    assert client.get("/collections").json()[0]["certificate_ids"] == [cert["id"]]
    assert client.post("/collections", json={"name": "Next chapter"}).status_code == 409
    with TestClient(app) as other:
        other.post("/auth/demo")
        assert other.get("/collections").json() == []
        assert (
            other.post(
                "/collections", json={"name": "Illegal", "certificate_ids": [cert["id"]]}
            ).status_code
            == 404
        )
        assert (
            other.put(f"/collections/{created['id']}", json={"name": "Not mine"}).status_code == 404
        )
        assert (
            other.post(
                "/certificates/bulk", json={"certificate_ids": [cert["id"]], "action": "trash"}
            ).status_code
            == 404
        )
        assert other.get("/collections").json() == []
    assert (
        client.post(
            "/certificates/bulk", json={"certificate_ids": [cert["id"]], "action": "favorite"}
        ).status_code
        == 200
    )
    assert client.get(f"/certificates/{cert['id']}").json()["favorite"]
    assert (
        client.post(
            "/certificates/bulk", json={"certificate_ids": [cert["id"]], "action": "trash"}
        ).status_code
        == 200
    )
    assert client.get("/collections").json()[0]["certificate_ids"] == []
    client.post("/certificates/bulk", json={"certificate_ids": [cert["id"]], "action": "restore"})
    assert client.get("/collections").json()[0]["certificate_ids"] == [cert["id"]]
    assert (
        client.put(
            f"/collections/{created['id']}", json={"name": "Renamed", "certificate_ids": []}
        ).status_code
        == 200
    )


def test_bulk_validation_is_atomic(imported):
    client, _ = imported
    cert = client.get("/certificates").json()[0]
    response = client.post(
        "/certificates/bulk",
        json={"certificate_ids": [cert["id"], "does-not-exist"], "action": "trash"},
    )
    assert response.status_code == 404
    assert not client.get(f"/certificates/{cert['id']}").json()["trashed"]
