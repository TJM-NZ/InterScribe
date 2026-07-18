"""Gate 2 — QUOTE_GROUNDING validity checks (SPEC-003)."""
from datetime import datetime, timezone

import pytest

from app.models.phase2 import Phase2Chunk, QuoteCandidate
from app.models.video import JobStatus, MediaType, SpeakerRoleMap, TranscriptSegment, Video
from app.worker.phase2.grounding import apply_grounding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(db):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=JobStatus.phase2_processing,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def _make_segment(db, video_id, seg_id, speaker):
    s = TranscriptSegment(
        video_id=video_id,
        segment_id=seg_id,
        start_ts=float(seg_id),
        end_ts=float(seg_id + 1),
        text=f"Segment {seg_id} text.",
        speaker_label=speaker,
        confidence=0.9,
    )
    db.add(s)
    return s


def _make_role(db, video_id, speaker, role):
    db.add(SpeakerRoleMap(video_id=video_id, speaker_label=speaker, role=role))


def _make_chunk(db, video_id):
    c = Phase2Chunk(
        video_id=video_id, chunk_index=0,
        start_segment_id=0, end_segment_id=9, token_count=500,
    )
    db.add(c)
    db.flush()
    return c


def _make_candidate(db, video_id, chunk_id, start_seg, end_seg, speaker, discarded=False):
    c = QuoteCandidate(
        phase2_chunk_id=chunk_id,
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        speaker_label=speaker,
        narrative_alignment_score=0.5,
        is_notable_moment=False,
        raw_qwen_output={"candidates": []},
        discarded=discarded,
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_interviewee_candidate_not_discarded(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_01")
    s1 = _make_segment(db, v.id, 1, "SPEAKER_01")
    _make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = _make_chunk(db, v.id)
    cand = _make_candidate(db, v.id, chunk.id, 0, 1, "SPEAKER_01")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is False
    assert cand.discard_reason is None


def test_multi_speaker_range_discarded(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_00")
    s1 = _make_segment(db, v.id, 1, "SPEAKER_01")
    _make_role(db, v.id, "SPEAKER_00", "interviewer")
    _make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = _make_chunk(db, v.id)
    # Range spans both speakers
    cand = _make_candidate(db, v.id, chunk.id, 0, 1, "SPEAKER_00")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert cand.discard_reason == "multi_speaker_range"


def test_interviewer_speaker_discarded(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_00")
    s1 = _make_segment(db, v.id, 1, "SPEAKER_00")
    _make_role(db, v.id, "SPEAKER_00", "interviewer")
    chunk = _make_chunk(db, v.id)
    cand = _make_candidate(db, v.id, chunk.id, 0, 1, "SPEAKER_00")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert "non_interviewee_speaker" in cand.discard_reason
    assert "interviewer" in cand.discard_reason


def test_unknown_role_speaker_discarded(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_02")
    _make_role(db, v.id, "SPEAKER_02", "unknown")
    chunk = _make_chunk(db, v.id)
    cand = _make_candidate(db, v.id, chunk.id, 0, 0, "SPEAKER_02")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert "unknown" in cand.discard_reason


def test_speaker_not_in_role_map_discarded(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_99")
    # No SpeakerRoleMap row for SPEAKER_99
    chunk = _make_chunk(db, v.id)
    cand = _make_candidate(db, v.id, chunk.id, 0, 0, "SPEAKER_99")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True


def test_already_discarded_candidate_not_re_processed(db):
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_01")
    _make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = _make_chunk(db, v.id)
    # Already discarded by extraction (out-of-bounds, say), with a reason set
    cand = _make_candidate(db, v.id, chunk.id, 0, 0, "SPEAKER_01", discarded=True)
    cand.discard_reason = "out_of_bounds"
    db.flush()
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    # Still discarded, original reason preserved
    assert cand.discarded is True
    assert cand.discard_reason == "out_of_bounds"


def test_mixed_candidates_only_invalid_discarded(db):
    v = _make_video(db)
    # SPEAKER_00 = interviewer, SPEAKER_01 = interviewee
    s0 = _make_segment(db, v.id, 0, "SPEAKER_00")
    s1 = _make_segment(db, v.id, 1, "SPEAKER_01")
    s2 = _make_segment(db, v.id, 2, "SPEAKER_01")
    _make_role(db, v.id, "SPEAKER_00", "interviewer")
    _make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = _make_chunk(db, v.id)

    bad = _make_candidate(db, v.id, chunk.id, 0, 0, "SPEAKER_00")   # interviewer
    good = _make_candidate(db, v.id, chunk.id, 1, 2, "SPEAKER_01")  # interviewee, single-speaker
    db.commit()

    segments_by_id = {0: s0, 1: s1, 2: s2}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(bad)
    db.refresh(good)
    assert bad.discarded is True
    assert good.discarded is False


def test_single_segment_range_accepted(db):
    """A one-segment candidate always has exactly one speaker."""
    v = _make_video(db)
    s0 = _make_segment(db, v.id, 0, "SPEAKER_01")
    _make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = _make_chunk(db, v.id)
    cand = _make_candidate(db, v.id, chunk.id, 0, 0, "SPEAKER_01")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is False
