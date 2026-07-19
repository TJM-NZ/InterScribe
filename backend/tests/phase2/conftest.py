"""Shared fixtures and helpers for Phase 2 tests."""
import uuid

from app.models.phase2 import Phase2Chunk, Quote, QuoteCandidate
from app.models.video import SpeakerRoleMap


def make_phase2_chunk(db, video_id, chunk_index=0, start_seg=0, end_seg=9, tokens=500):
    c = Phase2Chunk(
        video_id=video_id,
        chunk_index=chunk_index,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        token_count=tokens,
    )
    db.add(c)
    db.flush()
    return c


def make_candidate(
    db, video_id, chunk_id, start_seg, end_seg,
    speaker="SPEAKER_01", score=0.5, discarded=False, quote_type="substantive",
):
    c = QuoteCandidate(
        phase2_chunk_id=chunk_id,
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        speaker_label=speaker,
        quote_type=quote_type,
        narrative_alignment_score=score,
        is_notable_moment=False,
        raw_qwen_output={"candidates": []},
        discarded=discarded,
    )
    db.add(c)
    db.flush()
    return c


def make_quote(
    db,
    video_id,
    start_seg=0,
    end_seg=2,
    score=0.8,
    is_notable=False,
    notable_moment_id=None,
    text="This is a great quote.",
    speaker="SPEAKER_01",
    quote_type="substantive",
    headline_text=None,
):
    q = Quote(
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        start_ts=float(start_seg),
        end_ts=float(end_seg + 1),
        quote_text=text,
        speaker_label=speaker,
        quote_type=quote_type,
        headline_text=headline_text,
        narrative_alignment_score=score,
        is_notable_moment=is_notable,
        notable_moment_id=notable_moment_id,
        source_candidate_ids=[str(uuid.uuid4())],
    )
    db.add(q)
    db.flush()
    return q


def make_role(db, video_id, speaker, role):
    db.add(SpeakerRoleMap(video_id=video_id, speaker_label=speaker, role=role))
