"""Group adjacent same-speaker TranscriptSegments into TranscriptTurns.

Implements TURN_GROUPING anchor from SPEC-002. TranscriptTurn rows are
permanent — Spec 3 must reuse them as the unit fed to Qwen.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.phase1 import TranscriptTurn
from app.models.video import TranscriptSegment


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def build_turns(video_id, db: Session) -> list[TranscriptTurn]:
    """Create and persist TranscriptTurn rows for video_id. Returns them ordered by turn_index."""
    segments = (
        db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.video_id == video_id)
            .order_by(TranscriptSegment.segment_id)
        )
        .scalars()
        .all()
    )

    if not segments:
        return []

    turns: list[TranscriptTurn] = []
    turn_index = 0
    i = 0

    while i < len(segments):
        seg = segments[i]
        current_speaker = seg.speaker_label
        group = [seg]
        i += 1

        while i < len(segments) and segments[i].speaker_label == current_speaker:
            group.append(segments[i])
            i += 1

        combined = " ".join(s.text for s in group)
        turn = TranscriptTurn(
            video_id=video_id,
            turn_index=turn_index,
            speaker_label=current_speaker,
            start_segment_id=group[0].segment_id,
            end_segment_id=group[-1].segment_id,
            combined_text=combined,
            token_count=_estimate_tokens(combined),
        )
        db.add(turn)
        turns.append(turn)
        turn_index += 1

    db.flush()
    return turns
