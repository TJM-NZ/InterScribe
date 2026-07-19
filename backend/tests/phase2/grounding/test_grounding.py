"""Gate 2 — QUOTE_GROUNDING validity checks (SPEC-003)."""
from tests.conftest import make_video, make_segment
from tests.phase2.conftest import make_phase2_chunk, make_candidate, make_role
from app.worker.phase2.grounding import apply_grounding


def test_valid_interviewee_candidate_not_discarded(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_01")
    s1 = make_segment(db, v.id, 1, speaker="SPEAKER_01")
    make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 1, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is False
    assert cand.discard_reason is None


def test_multi_speaker_range_discarded(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_00")
    s1 = make_segment(db, v.id, 1, speaker="SPEAKER_01")
    make_role(db, v.id, "SPEAKER_00", "interviewer")
    make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = make_phase2_chunk(db, v.id)
    # Range spans both speakers
    cand = make_candidate(db, v.id, chunk.id, 0, 1, speaker="SPEAKER_00")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert cand.discard_reason == "multi_speaker_range"


def test_interviewer_speaker_discarded(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_00")
    s1 = make_segment(db, v.id, 1, speaker="SPEAKER_00")
    make_role(db, v.id, "SPEAKER_00", "interviewer")
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 1, speaker="SPEAKER_00")
    db.commit()

    segments_by_id = {0: s0, 1: s1}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert "non_interviewee_speaker" in cand.discard_reason
    assert "interviewer" in cand.discard_reason


def test_unknown_role_speaker_discarded(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_02")
    make_role(db, v.id, "SPEAKER_02", "unknown")
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 0, speaker="SPEAKER_02")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True
    assert "unknown" in cand.discard_reason


def test_speaker_not_in_role_map_discarded(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_99")
    # No SpeakerRoleMap row for SPEAKER_99
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 0, speaker="SPEAKER_99")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is True


def test_already_discarded_candidate_not_re_processed(db):
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_01")
    make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 0, speaker="SPEAKER_01", discarded=True)
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
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_00")
    s1 = make_segment(db, v.id, 1, speaker="SPEAKER_01")
    s2 = make_segment(db, v.id, 2, speaker="SPEAKER_01")
    make_role(db, v.id, "SPEAKER_00", "interviewer")
    make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = make_phase2_chunk(db, v.id)

    bad = make_candidate(db, v.id, chunk.id, 0, 0, speaker="SPEAKER_00")   # interviewer
    good = make_candidate(db, v.id, chunk.id, 1, 2, speaker="SPEAKER_01")  # interviewee, single-speaker
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
    v = make_video(db)
    s0 = make_segment(db, v.id, 0, speaker="SPEAKER_01")
    make_role(db, v.id, "SPEAKER_01", "interviewee")
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 0, speaker="SPEAKER_01")
    db.commit()

    segments_by_id = {0: s0}
    apply_grounding(v.id, segments_by_id, db)
    db.commit()

    db.refresh(cand)
    assert cand.discarded is False
