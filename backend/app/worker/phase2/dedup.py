"""Rule-based boundary deduplication and Quote promotion.

Implements QUOTE_DEDUP anchor from SPEC-003:
- Candidates from overlapping Phase2Chunks with similar segment ranges + text are merged
- Merge thresholds: segment overlap ratio > threshold AND SequenceMatcher ratio > threshold
- No LLM call — purely rule-based
- Canonical candidate = highest narrative_alignment_score in the merge group
- All non-discarded candidates produce exactly one Quote row (merged or solo)
"""
import difflib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.phase2 import Quote, QuoteCandidate
from app.models.video import TranscriptSegment

logger = logging.getLogger(__name__)


def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    intersection = max(0, min(a_end, b_end) - max(a_start, b_start) + 1)
    union = max(a_end, b_end) - min(a_start, b_start) + 1
    return intersection / union if union > 0 else 0.0


def _text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _assemble_text(
    start_sid: int, end_sid: int, segments_by_id: dict[int, TranscriptSegment]
) -> str:
    return " ".join(
        segments_by_id[sid].text
        for sid in range(start_sid, end_sid + 1)
        if sid in segments_by_id
    )


def run_dedup_and_promote(
    video_id,
    segments_by_id: dict[int, TranscriptSegment],
    overlap_ratio_threshold: float,
    text_sim_threshold: float,
    db: Session,
) -> None:
    """Merge boundary-duplicate candidates and promote each group to one Quote row."""
    candidates = (
        db.execute(
            select(QuoteCandidate)
            .where(QuoteCandidate.video_id == video_id)
            .where(QuoteCandidate.discarded.is_(False))
            .order_by(QuoteCandidate.start_segment_id)
        )
        .scalars()
        .all()
    )

    if not candidates:
        return

    cand_texts = {
        str(c.id): _assemble_text(c.start_segment_id, c.end_segment_id, segments_by_id)
        for c in candidates
    }

    used: set[str] = set()
    groups: list[list[QuoteCandidate]] = []

    for i, cand_a in enumerate(candidates):
        aid = str(cand_a.id)
        if aid in used:
            continue
        group = [cand_a]
        used.add(aid)

        for cand_b in candidates[i + 1:]:
            bid = str(cand_b.id)
            if bid in used:
                continue
            seg_ratio = _overlap_ratio(
                cand_a.start_segment_id, cand_a.end_segment_id,
                cand_b.start_segment_id, cand_b.end_segment_id,
            )
            if seg_ratio > overlap_ratio_threshold:
                text_ratio = _text_similarity(cand_texts[aid], cand_texts[bid])
                if text_ratio > text_sim_threshold:
                    group.append(cand_b)
                    used.add(bid)

        groups.append(group)

    for group in groups:
        canonical = max(group, key=lambda c: c.narrative_alignment_score)
        text = cand_texts[str(canonical.id)]

        seg_range = [
            segments_by_id[sid]
            for sid in range(canonical.start_segment_id, canonical.end_segment_id + 1)
            if sid in segments_by_id
        ]
        if not seg_range:
            continue

        quote = Quote(
            video_id=video_id,
            start_segment_id=canonical.start_segment_id,
            end_segment_id=canonical.end_segment_id,
            start_ts=seg_range[0].start_ts,
            end_ts=seg_range[-1].end_ts,
            quote_text=text,
            speaker_label=canonical.speaker_label,
            quote_type=canonical.quote_type,
            narrative_alignment_score=canonical.narrative_alignment_score,
            is_notable_moment=canonical.is_notable_moment,
            notable_moment_id=canonical.notable_moment_id,
            source_candidate_ids=[str(c.id) for c in group],
            reviewed=False,
        )
        db.add(quote)

    db.flush()
    logger.info("Promoted %d candidate groups to Quote rows for video %s", len(groups), video_id)
