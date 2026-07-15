"""Chunk TranscriptTurns into TranscriptChunk rows.

Implements CHUNK_SCHEMA anchor from SPEC-002:
- Target ~max_tokens per chunk (default 10,000)
- Never splits a TranscriptTurn across two chunks
- Chunk boundaries align to turn boundaries
- Chunks numbered sequentially (chunk_index 0-based)
"""
from sqlalchemy.orm import Session

from app.models.phase1 import TranscriptChunk, TranscriptTurn


def build_chunks(
    video_id, turns: list[TranscriptTurn], max_tokens: int, db: Session
) -> list[TranscriptChunk]:
    """Greedy chunking: fill until next turn would overflow, then close current chunk."""
    if not turns:
        return []

    chunk_groups: list[list[TranscriptTurn]] = []
    current: list[TranscriptTurn] = []
    current_tokens = 0

    for turn in turns:
        if current and current_tokens + turn.token_count > max_tokens:
            chunk_groups.append(current)
            current = [turn]
            current_tokens = turn.token_count
        else:
            current.append(turn)
            current_tokens += turn.token_count

    if current:
        chunk_groups.append(current)

    chunks: list[TranscriptChunk] = []
    for idx, group in enumerate(chunk_groups):
        chunk = TranscriptChunk(
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


def chunk_text_for_qwen(group: list[TranscriptTurn]) -> str:
    """Format a chunk's turns as labelled lines for the Qwen prompt."""
    lines = []
    for turn in group:
        seg_ref = (
            f"[seg {turn.start_segment_id}]"
            if turn.start_segment_id == turn.end_segment_id
            else f"[seg {turn.start_segment_id}-{turn.end_segment_id}]"
        )
        lines.append(f"{seg_ref} {turn.speaker_label}: {turn.combined_text}")
    return "\n".join(lines)
