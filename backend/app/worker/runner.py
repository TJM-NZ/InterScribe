import logging
import time

from sqlalchemy import select

from app.database import SessionLocal
from app.models.video import JobStatus, Video
from app.worker.transcription import transcribe_video
from app.worker.phase1.pipeline import process_phase1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5


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


def _run_transcription(video: Video, db) -> None:
    video.status = JobStatus.transcribing
    video.error_reason = None
    db.commit()
    try:
        transcribe_video(video, db)
        logger.info("Transcription complete for video %s", video.id)
    except Exception as exc:
        db.rollback()
        with SessionLocal() as err_db:
            v = err_db.get(Video, video.id)
            if v:
                v.status = JobStatus.failed
                v.error_reason = str(exc)[:500]
                err_db.commit()
        logger.error("Transcription failed for video %s: %s", video.id, exc)


def _run_phase1(video: Video, db) -> None:
    video.status = JobStatus.phase1_processing
    video.error_reason = None
    db.commit()
    try:
        process_phase1(video, db)
        logger.info("Phase 1 complete for video %s", video.id)
    except Exception as exc:
        db.rollback()
        with SessionLocal() as err_db:
            v = err_db.get(Video, video.id)
            if v:
                v.status = JobStatus.failed
                v.error_reason = str(exc)[:500]
                err_db.commit()
        logger.error("Phase 1 failed for video %s: %s", video.id, exc)


def run_worker():
    logger.info("Worker started")
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

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()
