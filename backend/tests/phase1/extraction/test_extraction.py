"""Gate 1 — Qwen narrative extraction (mocked)."""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.phase1 import ChunkNarrative, NotableMoment, TranscriptChunk
from app.models.video import JobStatus, MediaType, Video
from app.worker.phase1.extraction import extract_chunk, _validate_notable_moments


def _make_video(db):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=JobStatus.phase1_processing,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def _make_chunk(db, video_id, start_seg=0, end_seg=9):
    c = TranscriptChunk(
        video_id=video_id,
        chunk_index=0,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        token_count=500,
    )
    db.add(c)
    db.flush()
    return c


_MOCK_QWEN_RESPONSE = {
    "domain": "AI research",
    "tone": "technical",
    "topic_tags": ["machine learning", "neural networks", "training"],
    "notable_moments": [
        {"start_segment_id": 2, "end_segment_id": 4, "description": "Key insight about scaling"},
    ],
}


def _mock_httpx_post(url, json=None, timeout=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": json_str(_MOCK_QWEN_RESPONSE)}}
    return resp


def json_str(d):
    import json
    return json.dumps(d)


def test_extract_chunk_creates_narrative_row(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"message": {"content": json_str(_MOCK_QWEN_RESPONSE)}}),
        )
        narrative = extract_chunk(chunk, "mock chunk text", db)

    db.commit()

    assert narrative.domain == "AI research"
    assert narrative.tone == "technical"
    assert "machine learning" in narrative.topic_tags
    assert narrative.chunk_id == chunk.id
    assert narrative.video_id == v.id


def test_extract_chunk_creates_notable_moments(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id, start_seg=0, end_seg=9)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"message": {"content": json_str(_MOCK_QWEN_RESPONSE)}}),
        )
        extract_chunk(chunk, "mock chunk text", db)

    db.commit()

    moments = db.query(NotableMoment).filter_by(video_id=v.id).all()
    assert len(moments) == 1
    assert moments[0].start_segment_id == 2
    assert moments[0].end_segment_id == 4
    assert "scaling" in moments[0].description


def test_extract_chunk_no_notable_moments(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id)
    db.commit()

    empty_response = {**_MOCK_QWEN_RESPONSE, "notable_moments": []}
    with patch("app.worker.phase1.extraction.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"message": {"content": json_str(empty_response)}}),
        )
        extract_chunk(chunk, "text", db)

    db.commit()

    moments = db.query(NotableMoment).filter_by(video_id=v.id).all()
    assert len(moments) == 0


def test_extract_chunk_retries_on_failure(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id)
    db.commit()

    call_count = 0

    def flaky_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("timeout")
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"message": {"content": json_str(_MOCK_QWEN_RESPONSE)}}
        return m

    with patch("app.worker.phase1.extraction.httpx.post", side_effect=flaky_post):
        with patch("app.worker.phase1.extraction.time.sleep"):
            narrative = extract_chunk(chunk, "text", db)

    assert call_count == 2
    assert narrative.domain == "AI research"


def test_extract_chunk_fails_after_all_retries(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post", side_effect=ConnectionError("always fails")):
        with patch("app.worker.phase1.extraction.time.sleep"):
            with pytest.raises(RuntimeError, match="Chunk 0 failed"):
                extract_chunk(chunk, "text", db)


def test_validate_notable_moments_clamps_out_of_range():
    moments = _validate_notable_moments(
        [{"start_segment_id": -5, "end_segment_id": 100, "description": "oob"}],
        chunk_start=0,
        chunk_end=9,
    )
    assert len(moments) == 1
    assert moments[0]["start_segment_id"] == 0
    assert moments[0]["end_segment_id"] == 9


def test_validate_notable_moments_skips_missing_description():
    moments = _validate_notable_moments(
        [{"start_segment_id": 0, "end_segment_id": 2, "description": ""}],
        chunk_start=0,
        chunk_end=9,
    )
    assert len(moments) == 0
