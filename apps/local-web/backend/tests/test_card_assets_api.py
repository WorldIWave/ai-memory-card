PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_create_draft_asset_namespace(memory_client):
    response = memory_client.post("/api/assets/cards/drafts")

    assert response.status_code == 201
    body = response.json()
    assert body["draft_id"].startswith("draft_")


def test_upload_and_read_draft_image(memory_client):
    draft_id = memory_client.post("/api/assets/cards/drafts").json()["draft_id"]

    upload = memory_client.post(
        "/api/assets/cards/upload",
        data={"draft_id": draft_id},
        files={"file": ("formula.png", PNG_BYTES, "image/png")},
    )

    assert upload.status_code == 201
    body = upload.json()
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(PNG_BYTES)
    assert body["markdown"].startswith("![formula]")
    assert body["url"].startswith(f"/api/assets/cards/drafts/{draft_id}/")

    read = memory_client.get(body["url"])
    assert read.status_code == 200
    assert read.content == PNG_BYTES
    assert read.headers["content-type"].startswith("image/png")


def test_upload_rejects_unsupported_file_type(memory_client):
    draft_id = memory_client.post("/api/assets/cards/drafts").json()["draft_id"]

    response = memory_client.post(
        "/api/assets/cards/upload",
        data={"draft_id": draft_id},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported image type" in response.json()["detail"]


def test_upload_rejects_missing_namespace(memory_client):
    response = memory_client.post(
        "/api/assets/cards/upload",
        files={"file": ("formula.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 400
    assert "card_id or draft_id is required" in response.json()["detail"]


def test_asset_route_rejects_path_traversal(memory_client):
    response = memory_client.get("/api/assets/cards/drafts/../../secret.png")

    assert response.status_code in {400, 404, 422}
