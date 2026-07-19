"""Gate 2 — Rule-based boundary dedup and Quote promotion (SPEC-003 QUOTE_DEDUP anchor)."""
import pytest

from app.models.phase2 import Quote
from app.models.video import TranscriptSegment
from tests.conftest import make_video, make_segment
from tests.phase2.conftest import make_phase2_chunk, make_candidate
from app.worker.phase2.dedup import _overlap_ratio, _text_similarity, run_dedup_and_promote


OVERLAP_RATIO = 0.5
TEXT_SIM = 0.85


def _segments_by_id(segs):
    return {s.segment_id: s for s in segs}


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------

def test_overlap_ratio_identical_ranges():
    assert _overlap_ratio(2, 5, 2, 5) == pytest.approx(1.0)


def test_overlap_ratio_no_overlap():
    assert _overlap_ratio(0, 2, 5, 8) == pytest.approx(0.0)


def test_overlap_ratio_partial():
    # intersection [3,5]=3, union [2,6]=5
    ratio = _overlap_ratio(2, 5, 3, 6)
    assert ratio == pytest.approx(3 / 5)


def test_overlap_ratio_one_inside_other():
    # [3,4] inside [2,6]: intersection=2, union=5
    ratio = _overlap_ratio(2, 6, 3, 4)
    assert ratio == pytest.approx(2 / 5)


def test_text_similarity_identical():
    assert _text_similarity("hello world", "hello world") == pytest.approx(1.0)


def test_text_similarity_very_different():
    assert _text_similarity("hello", "completely different") < 0.5


# ---------------------------------------------------------------------------
# Integration tests — run_dedup_and_promote
# ---------------------------------------------------------------------------

def test_solo_candidate_produces_one_quote(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text=f"Word{i}") for i in range(5)]
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 4, score=0.7)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v.id).all()
    assert len(quotes) == 1
    assert str(cand.id) in quotes[0].source_candidate_ids


def test_no_candidates_produces_no_quotes(db):
    v = make_video(db)
    db.commit()

    run_dedup_and_promote(v.id, {}, OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    assert db.query(Quote).filter_by(video_id=v.id).count() == 0


def test_discarded_candidates_not_promoted(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text=f"Word{i}") for i in range(3)]
    chunk = make_phase2_chunk(db, v.id)
    make_candidate(db, v.id, chunk.id, 0, 2, discarded=True)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    assert db.query(Quote).filter_by(video_id=v.id).count() == 0


def test_high_overlap_and_text_sim_merges_into_one_quote(db):
    v = make_video(db)
    # All segments use identical text so cand_a and cand_b texts are near-identical.
    # cand_a [0,4]: "hello hello hello hello hello"
    # cand_b [1,5]: "hello hello hello hello hello"
    # overlap_ratio([0,4],[1,5]) = 4/6 ≈ 0.667 > 0.5; text_sim = 1.0 > 0.85 → merge
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    cand_a = make_candidate(db, v.id, chunk.id, 0, 4, score=0.6)
    cand_b = make_candidate(db, v.id, chunk.id, 1, 5, score=0.8)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v.id).all()
    assert len(quotes) == 1
    q = quotes[0]
    assert str(cand_a.id) in q.source_candidate_ids
    assert str(cand_b.id) in q.source_candidate_ids


def test_canonical_is_highest_score_in_merged_group(db):
    v = make_video(db)
    # Identical-text segments so text_sim = 1.0, overlap_ratio([0,4],[1,5]) ≈ 0.667 → merge
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    cand_low = make_candidate(db, v.id, chunk.id, 0, 4, score=0.4)
    cand_high = make_candidate(db, v.id, chunk.id, 1, 5, score=0.9)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v.id).all()
    assert len(quotes) == 1
    assert quotes[0].narrative_alignment_score == pytest.approx(0.9)
    # Quote segment range matches the canonical (high-score) candidate
    assert quotes[0].start_segment_id == 1
    assert quotes[0].end_segment_id == 5


def test_low_text_sim_produces_separate_quotes(db):
    v = make_video(db)
    texts = ["alpha beta", "gamma delta", "epsilon zeta", "xyz abc", "foo bar", "qux quux", "baz boo"]
    v2 = make_video(db)
    segs = [make_segment(db, v2.id, i, text=t) for i, t in enumerate(texts)]
    chunk2 = make_phase2_chunk(db, v2.id)
    # High overlap ratio but text quite different (non-repetitive unique words)
    # segments 0-4 text: "alpha beta gamma delta epsilon zeta xyz abc foo bar"
    # segments 2-6 text: "epsilon zeta xyz abc foo bar qux quux baz boo"
    # SequenceMatcher on these should be < 0.85
    make_candidate(db, v2.id, chunk2.id, 0, 4, score=0.5)
    make_candidate(db, v2.id, chunk2.id, 2, 6, score=0.6)
    db.commit()

    by_id = {s.segment_id: s for s in segs}
    run_dedup_and_promote(v2.id, by_id, OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v2.id).all()
    assert len(quotes) == 2


def test_non_overlapping_ranges_produce_separate_quotes(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text=f"Word{i}") for i in range(10)]
    chunk = make_phase2_chunk(db, v.id)
    cand_a = make_candidate(db, v.id, chunk.id, 0, 2, score=0.5)
    cand_b = make_candidate(db, v.id, chunk.id, 7, 9, score=0.6)
    db.commit()

    # overlap_ratio([0,2],[7,9]) = 0 → no merge
    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v.id).all()
    assert len(quotes) == 2


def test_quote_timestamps_from_canonical_segments(db):
    v = make_video(db)
    segs = []
    for i in range(5):
        s = TranscriptSegment(
            video_id=v.id, segment_id=i,
            start_ts=float(i * 2),
            end_ts=float(i * 2 + 1.5),
            text=f"Word{i}",
            speaker_label="SPEAKER_01",
            confidence=0.9,
        )
        db.add(s)
        segs.append(s)
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 1, 3, score=0.7)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.start_ts == pytest.approx(segs[1].start_ts)
    assert q.end_ts == pytest.approx(segs[3].end_ts)


def test_quote_text_assembled_from_segments(db):
    v = make_video(db)
    texts = ["Hello", "world", "this", "is", "a", "test"]
    segs = [make_segment(db, v.id, i, text=texts[i]) for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 1, 4, score=0.5)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.quote_text == "world this is a"


def test_quote_speaker_label_from_canonical(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, speaker="SPEAKER_01", text=f"Word{i}") for i in range(5)]
    chunk = make_phase2_chunk(db, v.id)
    cand = make_candidate(db, v.id, chunk.id, 0, 4, score=0.5, speaker="SPEAKER_01")
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.speaker_label == "SPEAKER_01"


def test_reviewed_defaults_false_on_new_quote(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text=f"Word{i}") for i in range(3)]
    chunk = make_phase2_chunk(db, v.id)
    make_candidate(db, v.id, chunk.id, 0, 2, score=0.5)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.reviewed is False


# ---------------------------------------------------------------------------
# quote_type dedup propagation (SPEC-003-FIX-001)
# ---------------------------------------------------------------------------

def test_dedup_both_headline_promotes_headline(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    make_candidate(db, v.id, chunk.id, 0, 4, score=0.6, quote_type="headline")
    make_candidate(db, v.id, chunk.id, 1, 5, score=0.8, quote_type="headline")
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.quote_type == "headline"


def test_dedup_both_substantive_promotes_substantive(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    make_candidate(db, v.id, chunk.id, 0, 4, score=0.5, quote_type="substantive")
    make_candidate(db, v.id, chunk.id, 1, 5, score=0.7, quote_type="substantive")
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.quote_type == "substantive"


def test_dedup_mixed_type_headline_higher_score_promotes_headline(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    # headline has higher score → canonical is headline
    make_candidate(db, v.id, chunk.id, 0, 4, score=0.9, quote_type="headline")
    make_candidate(db, v.id, chunk.id, 1, 5, score=0.4, quote_type="substantive")
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.quote_type == "headline"


def test_dedup_mixed_type_substantive_higher_score_promotes_substantive(db):
    v = make_video(db)
    segs = [make_segment(db, v.id, i, text="hello") for i in range(6)]
    chunk = make_phase2_chunk(db, v.id)
    # substantive has higher score → canonical is substantive
    make_candidate(db, v.id, chunk.id, 0, 4, score=0.3, quote_type="headline")
    make_candidate(db, v.id, chunk.id, 1, 5, score=0.8, quote_type="substantive")
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    q = db.query(Quote).filter_by(video_id=v.id).one()
    assert q.quote_type == "substantive"


def test_three_candidates_two_merged_one_solo(db):
    v = make_video(db)
    # Segments 0-8: identical text so cand_a [0,5] and cand_b [1,6] merge (text_sim=1.0)
    # Segments 10-11: different text so cand_c is solo
    segs = [make_segment(db, v.id, i, text="hello" if i < 9 else f"Word{i}") for i in range(12)]
    chunk = make_phase2_chunk(db, v.id)
    cand_a = make_candidate(db, v.id, chunk.id, 0, 5, score=0.5)
    cand_b = make_candidate(db, v.id, chunk.id, 1, 6, score=0.7)
    # [10,11]: no overlap with above
    cand_c = make_candidate(db, v.id, chunk.id, 10, 11, score=0.6)
    db.commit()

    run_dedup_and_promote(v.id, _segments_by_id(segs), OVERLAP_RATIO, TEXT_SIM, db)
    db.commit()

    quotes = db.query(Quote).filter_by(video_id=v.id).order_by(Quote.start_segment_id).all()
    assert len(quotes) == 2
    solo = [q for q in quotes if str(cand_c.id) in q.source_candidate_ids]
    assert len(solo) == 1
