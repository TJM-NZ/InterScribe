import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.phase2 import Quote, QuoteType
from app.models.video import JobStatus, ProcessingPhase, ProcessingRun, Video
from app.worker.transcription import transcribe_video
from app.worker.phase1.extraction import unload_qwen_model
from app.worker.phase1.pipeline import process_phase1
from app.worker.phase2.pipeline import process_phase2
from app.worker.condensation.pipeline import process_condensation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5

_STUCK_STATES = {
    JobStatus.transcribing: JobStatus.queued,
    JobStatus.phase1_processing: JobStatus.phase1_queued,
    JobStatus.phase2_processing: JobStatus.phase2_queued,
    JobStatus.condensation_processing: JobStatus.condensation_queued,
}


def _recover_stuck_jobs(db) -> None:
    for processing_status, queued_status in _STUCK_STATES.items():
        stuck = db.execute(
            select(Video).where(Video.status == processing_status)
        ).scalars().all()
        for v in stuck:
            logger.warning(
                "Recovering stuck job: %s (%s) %s → %s",
                v.id, v.original_filename, processing_status.value, queued_status.value,
            )
            v.status = queued_status
    db.commit()


def _pick_next(db, status: JobStatus) -> Video | None:
    return db.execute(
        select(Video)
        .where(Video.status == status)
        .order_by(Video.uploaded_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()


def _run_pipeline(
    video: Video,
    db,
    processing_status: JobStatus,
    pipeline_fn: Callable,
    label: str,
    phase: ProcessingPhase,
    *,
    unload_gpu: bool = False,
) -> None:
    video.status = processing_status
    video.error_reason = None

    max_run = db.execute(
        select(func.max(ProcessingRun.run_number))
        .where(ProcessingRun.video_id == video.id)
        .where(ProcessingRun.phase == phase)
    ).scalar() or 0
    started_at = datetime.now(timezone.utc)
    run = ProcessingRun(
        video_id=video.id,
        phase=phase,
        run_number=max_run + 1,
        started_at=started_at,
    )
    db.add(run)
    run_id = run.id
    db.commit()

    try:
        pipeline_fn(video, db)
        completed_at = datetime.now(timezone.utc)
        run.completed_at = completed_at
        run.wall_seconds = (completed_at - started_at).total_seconds()
        run.succeeded = True
        db.commit()
        logger.info("%s complete for video %s (%.1fs)", label, video.id, run.wall_seconds)
    except Exception as exc:
        db.rollback()
        completed_at = datetime.now(timezone.utc)
        with SessionLocal() as err_db:
            v = err_db.get(Video, video.id)
            if v:
                v.status = JobStatus.failed
                v.error_reason = str(exc)[:500]
                err_db.commit()
            r = err_db.get(ProcessingRun, run_id)
            if r:
                r.completed_at = completed_at
                r.wall_seconds = (completed_at - started_at).total_seconds()
                r.succeeded = False
                r.error_reason = str(exc)[:500]
                err_db.commit()
        logger.error("%s failed for video %s: %s", label, video.id, exc)
    finally:
        if unload_gpu:
            unload_qwen_model()


def run_worker():
    logger.info("Worker started")
    with SessionLocal() as db:
        _recover_stuck_jobs(db)
    while True:
        with SessionLocal() as db:
            video = _pick_next(db, JobStatus.queued)
            if video is not None:
                logger.info("Transcribing video %s (%s)", video.id, video.original_filename)
                _run_pipeline(video, db, JobStatus.transcribing, transcribe_video, "Transcription", ProcessingPhase.transcription)
                continue

            video = _pick_next(db, JobStatus.phase1_queued)
            if video is not None:
                logger.info("Phase 1 processing video %s (%s)", video.id, video.original_filename)
                _run_pipeline(video, db, JobStatus.phase1_processing, process_phase1, "Phase 1", ProcessingPhase.phase1, unload_gpu=True)
                continue

            video = _pick_next(db, JobStatus.phase2_queued)
            if video is not None:
                logger.info("Phase 2 processing video %s (%s)", video.id, video.original_filename)
                _run_pipeline(video, db, JobStatus.phase2_processing, process_phase2, "Phase 2", ProcessingPhase.phase2, unload_gpu=True)
                continue

            video = _pick_next(db, JobStatus.condensation_queued)
            if video is not None:
                headline_count = db.execute(
                    select(func.count(Quote.id))
                    .where(Quote.video_id == video.id)
                    .where(Quote.quote_type == QuoteType.headline)
                ).scalar() or 0
                if headline_count == 0:
                    logger.info(
                        "No headline quotes for video %s — skipping condensation", video.id
                    )
                    now = datetime.now(timezone.utc)
                    max_run = db.execute(
                        select(func.max(ProcessingRun.run_number))
                        .where(ProcessingRun.video_id == video.id)
                        .where(ProcessingRun.phase == ProcessingPhase.condensation)
                    ).scalar() or 0
                    db.add(ProcessingRun(
                        video_id=video.id,
                        phase=ProcessingPhase.condensation,
                        run_number=max_run + 1,
                        started_at=now,
                        completed_at=now,
                        wall_seconds=0.0,
                        succeeded=True,
                    ))
                    video.status = JobStatus.condensation_reviewed
                    db.commit()
                else:
                    logger.info(
                        "Condensation processing video %s (%s)", video.id, video.original_filename
                    )
                    _run_pipeline(
                        video, db,
                        JobStatus.condensation_processing,
                        process_condensation,
                        "Condensation",
                        ProcessingPhase.condensation,
                        unload_gpu=True,
                    )
                continue

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()
