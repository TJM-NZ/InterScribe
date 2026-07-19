"""Gate 1 — Qwen narrative extraction (mocked)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.phase1 import ChunkNarrative, ChunkTheme, NotableMoment
from tests.conftest import make_video
from tests.phase1.conftest import make_chunk
from app.worker.phase1.extraction import extract_chunk, _validate_notable_moments, _validate_themes


_MOCK_QWEN_RESPONSE = {
    "domain": "AI research",
    "tone": "technical",
    "themes": [
        {
            "topic_focus": "Discussion of neural network scaling laws and their implications.",
            "topic_tags": ["machine learning", "neural networks", "scaling"],
            "start_segment_id": 0,
            "end_segment_id": 4,
            "notable_moments": [
                {"start_segment_id": 2, "end_segment_id": 4, "description": "Key insight about scaling"},
            ],
        },
        {
            "topic_focus": "Practical challenges in training large models.",
            "topic_tags": ["training", "compute", "hardware"],
            "start_segment_id": 5,
            "end_segment_id": 9,
            "notable_moments": [],
        },
    ],
}


def json_str(d):
    return json.dumps(d)


def _mock_post(response_dict):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"message": {"content": json_str(response_dict)}}
    return m


def test_extract_chunk_creates_narrative_row(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post", return_value=_mock_post(_MOCK_QWEN_RESPONSE)):
        narrative, themes = extract_chunk(chunk, "mock chunk text", db)

    db.commit()

    assert narrative.domain == "AI research"
    assert narrative.tone == "technical"
    assert narrative.chunk_id == chunk.id
    assert narrative.video_id == v.id


def test_extract_chunk_creates_theme_rows(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post", return_value=_mock_post(_MOCK_QWEN_RESPONSE)):
        _narrative, themes = extract_chunk(chunk, "mock chunk text", db)

    db.commit()

    assert len(themes) == 2
    assert themes[0].theme_index == 0
    assert "neural network" in themes[0].topic_focus
    assert "machine learning" in themes[0].topic_tags
    assert themes[1].theme_index == 1
    assert themes[0].chunk_id == chunk.id
    assert themes[0].video_id == v.id


def test_extract_chunk_creates_notable_moments_linked_to_theme(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
    db.commit()

    with patch("app.worker.phase1.extraction.httpx.post", return_value=_mock_post(_MOCK_QWEN_RESPONSE)):
        _narrative, themes = extract_chunk(chunk, "mock chunk text", db)

    db.commit()

    moments = db.query(NotableMoment).filter_by(video_id=v.id).all()
    assert len(moments) == 1
    assert moments[0].start_segment_id == 2
    assert moments[0].end_segment_id == 4
    assert "scaling" in moments[0].description
    assert moments[0].theme_id == themes[0].id


def test_extract_chunk_no_themes(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
    db.commit()

    empty_response = {**_MOCK_QWEN_RESPONSE, "themes": []}
    with patch("app.worker.phase1.extraction.httpx.post", return_value=_mock_post(empty_response)):
        _narrative, themes = extract_chunk(chunk, "text", db)

    db.commit()

    assert themes == []
    assert db.query(NotableMoment).filter_by(video_id=v.id).count() == 0


def test_extract_chunk_retries_on_failure(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
    db.commit()

    call_count = 0

    def flaky_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("timeout")
        return _mock_post(_MOCK_QWEN_RESPONSE)

    with patch("app.worker.phase1.extraction.httpx.post", side_effect=flaky_post):
        with patch("app.worker.phase1.extraction.time.sleep"):
            narrative, themes = extract_chunk(chunk, "text", db)

    assert call_count == 2
    assert narrative.domain == "AI research"


def test_extract_chunk_fails_after_all_retries(db):
    v = make_video(db)
    chunk = make_chunk(db, v.id)
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


def test_validate_themes_skips_missing_focus():
    themes = _validate_themes(
        [{"topic_focus": "", "topic_tags": ["ml"], "start_segment_id": 0, "end_segment_id": 5, "notable_moments": []}],
        chunk_start=0,
        chunk_end=9,
    )
    assert len(themes) == 0


def test_validate_themes_clamps_segment_ids():
    themes = _validate_themes(
        [{"topic_focus": "Some topic.", "topic_tags": [], "start_segment_id": -3, "end_segment_id": 100, "notable_moments": []}],
        chunk_start=0,
        chunk_end=9,
    )
    assert len(themes) == 1
    assert themes[0]["start_segment_id"] == 0
    assert themes[0]["end_segment_id"] == 9
