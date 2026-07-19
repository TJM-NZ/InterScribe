"""Orchestrate the full Phase 2 pipeline for a single video.

Flow: load turns → build overlapping Phase2Chunks → Qwen extraction per chunk
      → grounding validity checks → boundary dedup → promote to Quote rows
      → phase2_ready_for_review
"""
import logging

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.phase1 import ChunkTheme, NarrativeCluster, NotableMoment, TranscriptTurn
from app.models.phase2 import Phase2Chunk, Quote
from app.models.video import JobStatus, TranscriptSegment, Video
from app.worker.phase1.clustering import load_embedding_model
from app.worker.phase1.extraction import _pull_model_if_needed
from app.worker.phase2.chunking import build_phase2_chunks
from app.worker.phase2.dedup import run_dedup_and_promote
from app.worker.phase2.extraction import extract_phase2_chunk
from app.worker.phase2.grounding import apply_grounding

logger = logging.getLogger(__name__)


def process_phase2(video: Video, db: Session) -> None:
    _pull_model_if_needed()

    turns = (
        db.execute(
            select(TranscriptTurn)
            .where(TranscriptTurn.video_id == video.id)
            .order_by(TranscriptTurn.turn_index)
        )
        .scalars()
        .all()
    )

    if not turns:
        video.status = JobStatus.phase2_ready_for_review
        db.commit()
        return

    clusters = (
        db.execute(
            select(NarrativeCluster)
            .where(NarrativeCluster.video_id == video.id)
            .order_by(NarrativeCluster.rank)
            .limit(settings.narrative_top_n)
        )
        .scalars()
        .all()
    )

    cluster_ids = [c.id for c in clusters]
    if cluster_ids:
        themes = (
            db.execute(
                select(ChunkTheme).where(ChunkTheme.cluster_id.in_(cluster_ids))
            )
            .scalars()
            .all()
        )
        theme_embeddings = (
            np.array([np.array(t.theme_embedding) for t in themes]) if themes else None
        )
    else:
        theme_embeddings = None

    all_notable_moments = (
        db.execute(
            select(NotableMoment).where(NotableMoment.video_id == video.id)
        )
        .scalars()
        .all()
    )

    segments = (
        db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.video_id == video.id)
            .order_by(TranscriptSegment.segment_id)
        )
        .scalars()
        .all()
    )
    segments_by_id = {s.segment_id: s for s in segments}

    embedding_model = load_embedding_model()

    db.execute(delete(Quote).where(Quote.video_id == video.id))
    db.execute(delete(Phase2Chunk).where(Phase2Chunk.video_id == video.id))
    db.commit()

    logger.info("Phase 2: building overlapping chunks for video %s", video.id)
    chunks, chunk_groups = build_phase2_chunks(
        video.id, turns, settings.narrative_chunk_max_tokens, settings.phase2_overlap_turns, db
    )
    db.commit()

    logger.info("Phase 2: extracting quote candidates from %d chunks for video %s", len(chunks), video.id)
    for chunk, group in zip(chunks, chunk_groups):
        chunk_notable_moments = [
            m for m in all_notable_moments
            if m.start_segment_id <= chunk.end_segment_id and m.end_segment_id >= chunk.start_segment_id
        ]
        extract_phase2_chunk(
            chunk, group, clusters, chunk_notable_moments, all_notable_moments,
            segments_by_id, theme_embeddings, embedding_model, db,
        )
        db.commit()

    logger.info("Phase 2: applying grounding validity checks for video %s", video.id)
    apply_grounding(video.id, segments_by_id, db)
    db.commit()

    logger.info("Phase 2: deduplicating and promoting Quote rows for video %s", video.id)
    run_dedup_and_promote(
        video.id, segments_by_id,
        settings.phase2_dedup_overlap_ratio,
        settings.phase2_dedup_text_similarity,
        db,
    )
    db.commit()

    video.status = JobStatus.phase2_ready_for_review
    video.error_reason = None
    db.commit()
    logger.info("Phase 2 complete for video %s", video.id)
