"""Gate 2 — clustering (NARRATIVE_CLUSTER anchor)."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models.phase1 import ChunkTheme, NarrativeCluster, NotableMoment
from tests.conftest import make_video
from tests.phase1.conftest import make_chunk, make_theme
from app.worker.phase1.clustering import cluster_themes, _representative_label


def _make_chunk(db, video_id, chunk_index):
    # Segment IDs are chunk_index-relative for clustering geometry tests.
    return make_chunk(db, video_id, chunk_index, start_seg=chunk_index * 10, end_seg=chunk_index * 10 + 9, tokens=100)


def _make_theme(db, chunk, theme_index=0, focus="Test topic.", tags=None):
    # Clustering tests need zero embeddings for geometric clarity.
    return make_theme(db, chunk, theme_index=theme_index, focus=focus, tags=tags, embedding=[0.0] * 384)


def _mock_model(embeddings: list[list[float]]):
    model = MagicMock()
    model.encode.return_value = np.array(embeddings)
    return model


def test_single_theme_produces_one_cluster(db):
    v = make_video(db)
    chunk = _make_chunk(db, v.id, 0)
    theme = _make_theme(db, chunk)
    db.commit()

    model = _mock_model([[0.1] * 384])
    cluster_themes(v.id, [theme], {str(chunk.id): chunk}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    assert len(clusters) == 1
    assert clusters[0].cluster_size == 1
    assert clusters[0].rank == 1


def test_similar_themes_cluster_together(db):
    v = make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(3)]
    themes = [_make_theme(db, c) for c in chunks]
    db.commit()

    model = _mock_model([[1.0] + [0.0] * 383] * 3)
    cluster_themes(v.id, themes, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    assert len(clusters) == 1
    assert clusters[0].cluster_size == 3
    assert clusters[0].rank == 1


def test_distinct_themes_produce_separate_clusters(db):
    v = make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(4)]
    themes = [
        _make_theme(db, chunks[0], focus="AI topic."),
        _make_theme(db, chunks[1], focus="AI topic."),
        _make_theme(db, chunks[2], focus="Healthcare topic."),
        _make_theme(db, chunks[3], focus="Policy topic."),
    ]
    db.commit()

    embs = [
        [1.0, 0.0] + [0.0] * 382,
        [1.0, 0.0] + [0.0] * 382,
        [0.0, 1.0] + [0.0] * 382,
        [0.0, 0.0, 1.0] + [0.0] * 381,
    ]
    model = _mock_model(embs)
    cluster_themes(v.id, themes, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = db.query(NarrativeCluster).filter_by(video_id=v.id).all()
    sizes = sorted([c.cluster_size for c in clusters], reverse=True)
    assert sizes[0] == 2


def test_rank_by_size_descending(db):
    v = make_video(db)
    chunks = [_make_chunk(db, v.id, i) for i in range(4)]
    themes = [_make_theme(db, c) for c in chunks]
    db.commit()

    embs = [
        [1.0] + [0.0] * 383,
        [1.0] + [0.0] * 383,
        [0.0, 1.0] + [0.0] * 382,
        [0.0, 0.0, 1.0] + [0.0] * 381,
    ]
    model = _mock_model(embs)
    cluster_themes(v.id, themes, {str(c.id): c for c in chunks}, model, db)
    db.commit()

    clusters = sorted(
        db.query(NarrativeCluster).filter_by(video_id=v.id).all(),
        key=lambda c: c.rank,
    )
    assert clusters[0].cluster_size == 2
    assert clusters[0].rank == 1


def test_notable_moments_pass_through_even_if_singleton(db):
    """Sanity check: single notable moment in 8 chunks is present unconditionally."""
    v = make_video(db)
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


def test_representative_label_uses_top_tags():
    themes = [
        MagicMock(topic_focus="AI scaling.", topic_tags=["ml", "data"]),
        MagicMock(topic_focus="Ethics.", topic_tags=["ml", "ethics"]),
        MagicMock(topic_focus="Policy.", topic_tags=["policy"]),
    ]
    label = _representative_label(themes)
    assert "ml" in label
    assert "AI scaling" in label
