"""Gate 1 — Phase 2 quote candidate extraction (QUOTE_GROUNDING anchor)."""
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models.phase1 import NotableMoment, TranscriptChunk
from app.models.phase2 import QuoteCandidate
from app.models.video import JobStatus
from tests.conftest import make_video, make_segment
from tests.phase1.conftest import make_turn, make_chunk
from tests.phase2.conftest import make_phase2_chunk
from app.worker.phase2.extraction import (
    _compute_narrative_score,
    _find_notable_moment,
    _validate_candidates,
    extract_phase2_chunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segments(db, video_id, count=10, speaker="SPEAKER_01"):
    return [
        make_segment(db, video_id, i, speaker=speaker, text=f"Word{i} of the interview answer.")
        for i in range(count)
    ]


def _mock_qwen(candidates: list[dict]):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"message": {"content": json.dumps(candidates)}}
    return m


def _mock_model(vec=None):
    model = MagicMock()
    model.encode.return_value = np.array(vec or ([0.5] * 384))
    return model


_MOCK_CANDIDATES = [
    {"start_segment_id": 2, "end_segment_id": 5},
    {"start_segment_id": 7, "end_segment_id": 9},
]

# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------

def test_validate_candidates_keeps_valid():
    valid = _validate_candidates(_MOCK_CANDIDATES, chunk_start=0, chunk_end=9)
    assert len(valid) == 2


def test_validate_candidates_drops_out_of_bounds():
    raw = [{"start_segment_id": -1, "end_segment_id": 5}]
    assert _validate_candidates(raw, 0, 9) == []


def test_validate_candidates_drops_reversed_range():
    raw = [{"start_segment_id": 7, "end_segment_id": 3}]
    assert _validate_candidates(raw, 0, 9) == []


def test_validate_candidates_drops_missing_keys():
    assert _validate_candidates([{"start_segment_id": 2}], 0, 9) == []


def test_compute_narrative_score_with_embeddings():
    theme_embs = np.array([[1.0] + [0.0] * 383] * 3)
    model = _mock_model([1.0] + [0.0] * 383)
    score = _compute_narrative_score("some quote text", theme_embs, model)
    assert 0.0 <= score <= 1.0
    assert score > 0.9  # identical vectors → near 1.0


def test_compute_narrative_score_none_embeddings():
    model = _mock_model()
    score = _compute_narrative_score("text", None, model)
    assert score == 0.0


def test_find_notable_moment_overlap():
    moments = [
        MagicMock(start_segment_id=3, end_segment_id=6, id="m1"),
        MagicMock(start_segment_id=8, end_segment_id=9, id="m2"),
    ]
    result = _find_notable_moment(4, 5, moments)
    assert result.id == "m1"


def test_find_notable_moment_no_overlap():
    moments = [MagicMock(start_segment_id=8, end_segment_id=9, id="m1")]
    assert _find_notable_moment(0, 5, moments) is None


# ---------------------------------------------------------------------------
# Integration tests — extract_phase2_chunk
# ---------------------------------------------------------------------------

def test_extract_creates_candidate_rows(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    theme_embs = np.array([[0.5] * 384])

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, theme_embs, _mock_model(), db
        )

    db.commit()
    assert len(candidates) == 2
    rows = db.query(QuoteCandidate).filter_by(video_id=v.id).all()
    assert len(rows) == 2


def test_candidates_have_correct_segment_ids(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    assert candidates[0].start_segment_id == 2
    assert candidates[0].end_segment_id == 5
    assert candidates[1].start_segment_id == 7
    assert candidates[1].end_segment_id == 9


def test_narrative_alignment_score_is_float_in_range(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    theme_embs = np.array([[0.8] * 384])

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, theme_embs, _mock_model([0.8] * 384), db
        )

    for c in candidates:
        assert isinstance(c.narrative_alignment_score, float)
        assert 0.0 <= c.narrative_alignment_score <= 1.0


def test_is_notable_moment_set_on_overlap(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")

    p1_chunk = make_chunk(db, v.id)
    moment = NotableMoment(
        chunk_id=p1_chunk.id,
        video_id=v.id,
        start_segment_id=3,
        end_segment_id=6,
        description="Key insight",
    )
    db.add(moment)
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [moment], [moment], segments_by_id, None, _mock_model(), db
        )

    # candidate [2-5] overlaps moment [3-6]
    overlapping = [c for c in candidates if c.start_segment_id == 2]
    assert len(overlapping) == 1
    assert overlapping[0].is_notable_moment is True
    assert overlapping[0].notable_moment_id == moment.id


def test_is_notable_moment_false_when_no_overlap(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    assert all(not c.is_notable_moment for c in candidates)
    assert all(c.notable_moment_id is None for c in candidates)


def test_out_of_bounds_candidates_dropped(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    out_of_bounds = [{"start_segment_id": -1, "end_segment_id": 3}]

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(out_of_bounds)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    assert candidates == []


def test_raw_qwen_output_stored_on_candidate(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(_MOCK_CANDIDATES)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    for c in candidates:
        assert "start_segment_id" in c.raw_qwen_output
        assert c.discarded is False
        assert c.discard_reason is None


def test_empty_qwen_response_creates_no_candidates(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen([])):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    assert candidates == []


def test_retry_on_qwen_failure(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    call_count = 0

    def flaky_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("timeout")
        return _mock_qwen(_MOCK_CANDIDATES)

    with patch("app.worker.phase2.extraction.httpx.post", side_effect=flaky_post):
        with patch("app.worker.phase2.extraction.time.sleep"):
            candidates = extract_phase2_chunk(
                chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
            )

    assert call_count == 2
    assert len(candidates) == 2


def test_all_retries_exhausted_raises(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}

    with patch("app.worker.phase2.extraction.httpx.post", side_effect=ConnectionError("always fails")):
        with patch("app.worker.phase2.extraction.time.sleep"):
            with pytest.raises(RuntimeError, match="Phase 2 chunk 0 failed"):
                extract_phase2_chunk(
                    chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
                )


# ---------------------------------------------------------------------------
# quote_type classification (SPEC-003-FIX-001)
# ---------------------------------------------------------------------------

def test_validate_candidates_headline_type():
    raw = [{"start_segment_id": 2, "end_segment_id": 3, "type": "headline"}]
    result = _validate_candidates(raw, chunk_start=0, chunk_end=9)
    assert len(result) == 1
    assert result[0]["quote_type"] == "headline"


def test_validate_candidates_substantive_type():
    raw = [{"start_segment_id": 2, "end_segment_id": 5, "type": "substantive"}]
    result = _validate_candidates(raw, chunk_start=0, chunk_end=9)
    assert len(result) == 1
    assert result[0]["quote_type"] == "substantive"


def test_validate_candidates_missing_type_defaults_substantive():
    raw = [{"start_segment_id": 2, "end_segment_id": 5}]
    result = _validate_candidates(raw, chunk_start=0, chunk_end=9)
    assert len(result) == 1
    assert result[0]["quote_type"] == "substantive"


def test_validate_candidates_invalid_type_defaults_substantive():
    raw = [{"start_segment_id": 2, "end_segment_id": 5, "type": "pull_quote"}]
    result = _validate_candidates(raw, chunk_start=0, chunk_end=9)
    assert len(result) == 1
    assert result[0]["quote_type"] == "substantive"


def test_quote_type_stored_on_candidate(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    typed_candidates = [
        {"start_segment_id": 2, "end_segment_id": 3, "type": "headline"},
        {"start_segment_id": 7, "end_segment_id": 9, "type": "substantive"},
    ]

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(typed_candidates)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    db.commit()
    assert candidates[0].quote_type == "headline"
    assert candidates[1].quote_type == "substantive"


def test_quote_type_missing_from_qwen_defaults_substantive_on_candidate(db):
    v = make_video(db)
    segs = _make_segments(db, v.id)
    chunk = make_phase2_chunk(db, v.id)
    turn = make_turn(db, v.id, 0, 0, 9, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {s.segment_id: s for s in segs}
    no_type_candidates = [{"start_segment_id": 2, "end_segment_id": 5}]

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(no_type_candidates)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    db.commit()
    assert len(candidates) == 1
    assert candidates[0].quote_type == "substantive"


def test_speaker_label_taken_from_first_segment(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_00", text="Hello")
    s1 = make_segment(db, v.id, 1, speaker="SPEAKER_01", text="World")
    chunk = make_phase2_chunk(db, v.id, start_seg=0, end_seg=1)
    turn = make_turn(db, v.id, 0, 0, 1, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    raw = [{"start_segment_id": 0, "end_segment_id": 0}]

    with patch("app.worker.phase2.extraction.httpx.post", return_value=_mock_qwen(raw)):
        candidates = extract_phase2_chunk(
            chunk, [turn], [], [], [], segments_by_id, None, _mock_model(), db
        )

    assert len(candidates) == 1
    assert candidates[0].speaker_label == "SPEAKER_00"
