"""Orchestrate the full Phase 1 pipeline for a single video.

Flow: group segments → turns → chunks → Qwen extraction per chunk → cluster → phase1_ready_for_review
"""
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models.video import JobStatus, Video
from app.worker.phase1.chunking import build_chunks, chunk_text_for_qwen
from app.worker.phase1.clustering import cluster_narratives, load_embedding_model
from app.worker.phase1.extraction import extract_chunk, _pull_model_if_needed
from app.worker.phase1.turns import build_turns

logger = logging.getLogger(__name__)


def process_phase1(video: Video, db: Session) -> None:
    _pull_model_if_needed()

    logger.info("Phase 1: grouping segments into turns for video %s", video.id)
    turns = build_turns(video.id, db)

    if not turns:
        video.status = JobStatus.phase1_ready_for_review
        db.commit()
        return

    logger.info("Phase 1: chunking %d turns for video %s", len(turns), video.id)
    chunks, chunk_groups = build_chunks(
        video.id, turns, settings.narrative_chunk_max_tokens, db
    )
    db.commit()

    logger.info("Phase 1: extracting narrative from %d chunks for video %s", len(chunks), video.id)
    narratives = []
    for chunk, group in zip(chunks, chunk_groups):
        chunk_text = chunk_text_for_qwen(group)
        narrative = extract_chunk(chunk, chunk_text, db)
        narratives.append(narrative)
        db.commit()

    logger.info("Phase 1: clustering %d narratives for video %s", len(narratives), video.id)
    embedding_model = load_embedding_model()
    chunk_map = {str(c.id): c for c in chunks}
    cluster_narratives(video.id, narratives, chunk_map, embedding_model, db)
    db.commit()

    video.status = JobStatus.phase1_ready_for_review
    video.error_reason = None
    db.commit()
    logger.info("Phase 1 complete for video %s", video.id)
