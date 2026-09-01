"""Apply QUOTE_GROUNDING validity checks to QuoteCandidate rows.

SPEC-003 hard constraints:
- Candidates whose segment range spans more than one speaker_label are discarded
- Candidates whose speaker's role is not "interviewee" (per SpeakerRoleMap) are discarded
- Discarded rows are retained with discarded=True and discard_reason set
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.phase2 import QuoteCandidate
from app.models.video import SpeakerRoleMap, TranscriptSegment

logger = logging.getLogger(__name__)


def apply_grounding(video_id, segments_by_id: dict[int, TranscriptSegment], db: Session) -> None:
    """Validate all non-discarded QuoteCandidate rows for this video."""
    role_map: dict[str, str] = {
        r.speaker_label: r.role
        for r in db.execute(
            select(SpeakerRoleMap).where(SpeakerRoleMap.video_id == video_id)
        )
        .scalars()
        .all()
    }

    candidates = (
        db.execute(
            select(QuoteCandidate)
            .where(QuoteCandidate.video_id == video_id)
            .where(QuoteCandidate.discarded.is_(False))
        )
        .scalars()
        .all()
    )

    for cand in candidates:
        speakers_in_range = {
            segments_by_id[sid].speaker_label
            for sid in range(cand.start_segment_id, cand.end_segment_id + 1)
            if sid in segments_by_id
        }

        if len(speakers_in_range) > 1:
            cand.discarded = True
            cand.discard_reason = "multi_speaker_range"
            logger.debug("Discarded candidate %s: multi-speaker range", cand.id)
            continue

        role = role_map.get(cand.speaker_label)
        if role != "interviewee":
            cand.discarded = True
            cand.discard_reason = f"non_interviewee_speaker (role={role})"
            logger.debug("Discarded candidate %s: role=%s", cand.id, role)

    db.flush()
