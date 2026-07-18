import logging
import time
from collections.abc import Callable

from sqlalchemy import select

from app.database import SessionLocal
from app.models.video import JobStatus, Video
from app.worker.transcription import transcribe_video
from app.worker.phase1.extraction import unload_qwen_model
from app.worker.phase1.pipeline import process_phase1
from app.worker.phase2.pipeline import process_phase2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5

_STUCK_STATES = {
    JobStatus.transcribing: JobStatus.queued,
    JobStatus.phase1_processing: JobStatus.phase1_queued,
    JobStatus.phase2_processing: JobStatus.phase2_queued,
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


def _pick_next_transcription(db) -> Video | None:
    return db.execute(
        select(Video)
        .where(Video.status == JobStatus.queued)
        .order_by(Video.uploaded_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()


def _pick_next_phase1(db) -> Video | None:
    return db.execute(
        select(Video)
        .where(Video.status == JobStatus.phase1_queued)
        .order_by(Video.uploaded_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()


def _pick_next_phase2(db) -> Video | None:
    return db.execute(
        select(Video)
        .where(Video.status == JobStatus.phase2_queued)
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
    *,
    unload_gpu: bool = False,
) -> None:
    video.status = processing_status
    video.error_reason = None
    db.commit()
    try:
        pipeline_fn(video, db)
        logger.info("%s complete for video %s", label, video.id)
    except Exception as exc:
        db.rollback()
        with SessionLocal() as err_db:
            v = err_db.get(Video, video.id)
            if v:
                v.status = JobStatus.failed
                v.error_reason = str(exc)[:500]
                err_db.commit()
        logger.error("%s failed for video %s: %s", label, video.id, exc)
    finally:
        if unload_gpu:
            unload_qwen_model()


def _run_transcription(video: Video, db) -> None:
    _run_pipeline(video, db, JobStatus.transcribing, transcribe_video, "Transcription")


def _run_phase1(video: Video, db) -> None:
    _run_pipeline(video, db, JobStatus.phase1_processing, process_phase1, "Phase 1", unload_gpu=True)


def _run_phase2(video: Video, db) -> None:
    _run_pipeline(video, db, JobStatus.phase2_processing, process_phase2, "Phase 2", unload_gpu=True)


def run_worker():
    logger.info("Worker started")
    with SessionLocal() as db:
        _recover_stuck_jobs(db)
    while True:
        with SessionLocal() as db:
            video = _pick_next_transcription(db)
            if video is not None:
                logger.info("Transcribing video %s (%s)", video.id, video.original_filename)
                _run_transcription(video, db)
                continue

            video = _pick_next_phase1(db)
            if video is not None:
                logger.info("Phase 1 processing video %s (%s)", video.id, video.original_filename)
                _run_phase1(video, db)
                continue

            video = _pick_next_phase2(db)
            if video is not None:
                logger.info("Phase 2 processing video %s (%s)", video.id, video.original_filename)
                _run_phase2(video, db)
                continue

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()
