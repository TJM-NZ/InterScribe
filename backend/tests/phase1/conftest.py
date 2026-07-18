"""Shared fixtures and helpers for Phase 1 tests."""
from datetime import datetime, timezone

import pytest

from app.models.phase1 import ChunkTheme, NarrativeCluster, NotableMoment, TranscriptChunk, TranscriptTurn
from app.models.video import JobStatus, MediaType, Video


def make_video(db, status=JobStatus.phase1_processing):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def make_turn(db, video_id, turn_index, start_seg, end_seg, text="text", tokens=100, speaker="SPEAKER_00"):
    t = TranscriptTurn(
        video_id=video_id,
        turn_index=turn_index,
        speaker_label=speaker,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        combined_text=text,
        token_count=tokens,
    )
    db.add(t)
    db.flush()
    return t


def make_chunk(db, video_id, chunk_index=0, start_seg=0, end_seg=9, tokens=500):
    c = TranscriptChunk(
        video_id=video_id,
        chunk_index=chunk_index,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        token_count=tokens,
    )
    db.add(c)
    db.flush()
    return c


def make_theme(db, chunk, theme_index=0, focus="Test topic.", tags=None, start_seg=None, end_seg=None):
    t = ChunkTheme(
        chunk_id=chunk.id,
        video_id=chunk.video_id,
        theme_index=theme_index,
        topic_focus=focus,
        topic_tags=tags or ["ml"],
        start_segment_id=start_seg if start_seg is not None else chunk.start_segment_id,
        end_segment_id=end_seg if end_seg is not None else chunk.end_segment_id,
        theme_embedding=[0.1] * 384,
    )
    db.add(t)
    db.flush()
    return t


def make_cluster(db, video_id, rank=1, label="AI / technical", size=2):
    c = NarrativeCluster(
        video_id=video_id,
        representative_label=label,
        cluster_size=size,
        rank=rank,
    )
    db.add(c)
    db.flush()
    return c


def make_notable_moment(db, video_id, chunk_id, start_seg=0, end_seg=2, description="A key insight"):
    m = NotableMoment(
        chunk_id=chunk_id,
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        description=description,
    )
    db.add(m)
    db.flush()
    return m
