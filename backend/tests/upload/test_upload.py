import io
import os

import pytest

from tests.conftest import make_fake_audio


def _upload(client, content: bytes, filename: str = "test.wav", content_type: str = "audio/wav"):
    return client.post(
        "/api/videos",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def test_successful_upload_enqueues_job(client, mocker):
    mocker.patch("app.services.storage._probe_duration", return_value=60.0)
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="audio/wav")

    resp = _upload(client, make_fake_audio())
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "uploaded"
    assert "id" in data
    assert data["original_filename"] == "test.wav"
    assert data["media_type"] == "audio"


def test_media_type_video_detected(client, mocker):
    mocker.patch("app.services.storage._probe_duration", return_value=120.0)
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="video/mp4")

    resp = _upload(client, b"\x00" * 2048, filename="clip.mp4", content_type="video/mp4")
    assert resp.status_code == 201
    assert resp.json()["media_type"] == "video"


def test_unsupported_file_type_rejected(client, mocker):
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="application/pdf")

    resp = _upload(client, b"%PDF", filename="doc.pdf", content_type="application/pdf")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert "trace_id" in detail
    assert "storage_path" not in str(detail)


def test_oversized_upload_rejected(client, mocker):
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="audio/wav")

    os.environ["MAX_UPLOAD_SIZE_BYTES"] = "1000"
    from app import config
    config.settings.max_upload_size_bytes = 1000

    resp = _upload(client, make_fake_audio(size=2000))
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["code"] == "FILE_TOO_LARGE"

    config.settings.max_upload_size_bytes = 2_147_483_648


def test_duration_exceeded_rejected(client, mocker):
    mocker.patch("app.services.storage._probe_duration", return_value=99999.0)
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="audio/wav")

    resp = _upload(client, make_fake_audio())
    assert resp.status_code == 413


def test_video_status_polling(client, mocker):
    mocker.patch("app.services.storage._probe_duration", return_value=60.0)
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="audio/wav")

    create_resp = _upload(client, make_fake_audio())
    assert create_resp.status_code == 201
    video_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/videos/{video_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == video_id


def test_get_video_not_found(client):
    import uuid
    resp = client.get(f"/api/videos/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_error_response_has_no_path_or_stacktrace(client, mocker):
    mocker.patch("app.services.media_type.magic.from_buffer", return_value="application/octet-stream")

    resp = _upload(client, b"\x00" * 512, filename="unknown.bin", content_type="application/octet-stream")
    assert resp.status_code == 400
    detail_str = str(resp.json())
    assert "/home" not in detail_str
    assert "Traceback" not in detail_str
