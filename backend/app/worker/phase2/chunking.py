"""Build overlapping Phase2Chunk rows from TranscriptTurn rows.

Implements PHASE2_CHUNK anchor from SPEC-003:
- Target ~max_tokens per chunk (same default 10,000 as Phase 1)
- Never splits a TranscriptTurn across chunk boundaries
- Adjacent chunks overlap by overlap_turns whole turns at each boundary
- chunk_index is 0-based, sequential per video
"""
from sqlalchemy.orm import Session

from app.models.phase1 import TranscriptTurn
from app.models.phase2 import Phase2Chunk


def build_phase2_chunks(
    video_id,
    turns: list[TranscriptTurn],
    max_tokens: int,
    overlap_turns: int,
    db: Session,
) -> tuple[list[Phase2Chunk], list[list[TranscriptTurn]]]:
    """Greedy chunking with overlapping turn windows.

    Adjacent chunks share their last/first `overlap_turns` turns so a quote
    near a boundary is fully visible to at least one chunk's Qwen call.
    """
    if not turns:
        return [], []

    chunk_groups: list[list[TranscriptTurn]] = []
    i = 0

    while i < len(turns):
        current: list[TranscriptTurn] = []
        current_tokens = 0
        j = i

        while j < len(turns):
            turn = turns[j]
            if current and current_tokens + turn.token_count > max_tokens:
                break
            current.append(turn)
            current_tokens += turn.token_count
            j += 1

        if not current:
            # Single turn exceeds max_tokens — include it anyway to avoid infinite loop
            current = [turns[i]]
            j = i + 1

        chunk_groups.append(current)

        if j >= len(turns):
            # Consumed all remaining turns — no further chunks needed
            break

        # Next chunk starts overlap_turns before j; max(i+1, ...) guarantees progress
        i = max(i + 1, j - overlap_turns)

    chunks: list[Phase2Chunk] = []
    for idx, group in enumerate(chunk_groups):
        chunk = Phase2Chunk(
            video_id=video_id,
            chunk_index=idx,
            start_segment_id=group[0].start_segment_id,
            end_segment_id=group[-1].end_segment_id,
            token_count=sum(t.token_count for t in group),
        )
        db.add(chunk)
        chunks.append(chunk)

    db.flush()
    return chunks, chunk_groups
