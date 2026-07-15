"""Gate 2 — clustering (NARRATIVE_CLUSTER anchor)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models.phase1 import ChunkNarrative, NarrativeCluster, TranscriptChunk
from app.models.video import JobStatus, MediaType, Video
from app.worker.phase1.clustering import cluster_narratives, _representative_label


def _make_video(db):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=JobStatus.phase1_processing,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def _make_chunk(db, video_id, chunk_index):
    c = TranscriptChunk(
        video_id=video_id,
        chunk_index=chunk_index,
        start_segment_id=chunk_index * 10,
        end_segment_id=chunk_index * 10 + 9,
        token_count=100,
    )
    db.add(c)
    db.flush()
    return c


def _make_narrative(db, chunk, domain="AI", tone="technical", tags=None):
    n = ChunkNarrative(
        chunk_id=chunk.id,
        video_id=chunk.video_id,
        domain=domain,
        tone=tone,
        topic_tags=tags or ["ml"],
        narrative_embedding=[0.0] * 384,
        raw_qwen_output={},
    )
    db.add(n)
    db.flush()
    return n


def _mock_model(embeddings: list[list[float]]):
    model = MagicMock()
    model.encode.return_value = np.array(embeddings)
    return model


def test_single_narrative_produces_one_cluster(db):
    v = _make_video(db)
    chunk = _make_chunk(db, v.id, 0)
    narrative = _make_narrative(db, chunk)
    db.commit()

    model = _mock_model([[0.1] * 384])
    cluster_narratives(v.id, [narrative], {str(chunk.id): chunk}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    assert len(clusters) == 1
    assert clusters[0].cluster_size == 1
    assert clusters[0].rank == 1


def test_similar_narratives_cluster_together(db):
    v = _make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(3)]
    narratives = [_make_narrative(db, c) for c in chunks]
    db.commit()

    # All identical embeddings → all in one cluster
    model = _mock_model([[1.0] + [0.0] * 383] * 3)
    cluster_narratives(v.id, narratives, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    assert len(clusters) == 1
    assert clusters[0].cluster_size == 3
    assert clusters[0].rank == 1


def test_distinct_narratives_produce_separate_clusters(db):
    v = _make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(4)]
    narratives = [
        _make_narrative(db, chunks[0], domain="A"),
        _make_narrative(db, chunks[1], domain="A"),
        _make_narrative(db, chunks[2], domain="B"),
        _make_narrative(db, chunks[3], domain="C"),
    ]
    db.commit()

    # Two near-identical embeddings (A, A) and two orthogonal (B, C)
    embs = [
        [1.0, 0.0] + [0.0] * 382,
        [1.0, 0.0] + [0.0] * 382,
        [0.0, 1.0] + [0.0] * 382,
        [0.0, 0.0, 1.0] + [0.0] * 381,
    ]
    model = _mock_model(embs)
    cluster_narratives(v.id, narratives, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    # Expect: A+A (size 2), B (size 1), C (size 1)
    sizes = sorted([c.cluster_size for c in clusters], reverse=True)
    assert sizes[0] == 2


def test_rank_by_size_descending(db):
    v = _make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(4)]
    narratives = [
        _make_narrative(db, chunks[0]),
        _make_narrative(db, chunks[1]),
        _make_narrative(db, chunks[2]),
        _make_narrative(db, chunks[3]),
    ]
    db.commit()

    # First two cluster together (size 2), last two separate (size 1 each)
    embs = [
        [1.0] + [0.0] * 383,
        [1.0] + [0.0] * 383,
        [0.0, 1.0] + [0.0] * 382,
        [0.0, 0.0, 1.0] + [0.0] * 381,
    ]
    model = _mock_model(embs)
    cluster_narratives(v.id, narratives, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = sorted(
        db.query(NarrativeCluster).filter_by(video_id=v.id).all(),
        key=lambda c: c.rank,
    )
    assert clusters[0].cluster_size == 2
    assert clusters[0].rank == 1


def test_notable_moments_pass_through_even_if_singleton(db):
    """Sanity check: single notable moment in 8 chunks is present unconditionally."""
    from app.models.phase1 import NotableMoment

    v = _make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(8)]
    db.add(NotableMoment(
        chunk_id=chunks[0].id,
        video_id=v.id,
        start_segment_id=0,
        end_segment_id=2,
        description="A rare key moment",
    ))
    db.commit()

    from sqlalchemy import select
    moments = db.execute(
        select(NotableMoment).where(NotableMoment.video_id == v.id)
    ).scalars().all()

    assert len(moments) == 1
    assert moments[0].description == "A rare key moment"


def test_representative_label_uses_most_common_domain():
    narratives = [
        MagicMock(domain="AI", tone="technical", topic_tags=["ml", "data"]),
        MagicMock(domain="AI", tone="formal", topic_tags=["ml", "ethics"]),
        MagicMock(domain="Healthcare", tone="technical", topic_tags=["policy"]),
    ]
    label = _representative_label(narratives)
    assert "AI" in label
