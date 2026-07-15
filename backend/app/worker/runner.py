import logging
import time

from sqlalchemy import select

from app.database import SessionLocal
from app.models.video import JobStatus, Video
from app.worker.transcription import transcribe_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5


def _pick_next(db) -> Video | None:
    return db.execute(
        select(Video)
        .where(Video.status == JobStatus.queued)
        .order_by(Video.uploaded_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()


def run_worker():
    logger.info("Worker started")
    while True:
        with SessionLocal() as db:
            video = _pick_next(db)
            if video is None:
                time.sleep(POLL_INTERVAL)
                continue

            logger.info("Processing video %s (%s)", video.id, video.original_filename)
            video.status = JobStatus.transcribing
            video.error_reason = None
            db.commit()

            try:
                transcribe_video(video, db)
                logger.info("Completed video %s", video.id)
            except Exception as exc:
                db.rollback()
                with SessionLocal() as err_db:
                    v = err_db.get(Video, video.id)
                    if v:
                        v.status = JobStatus.failed
                        v.error_reason = str(exc)[:500]
                        err_db.commit()
                logger.error("Failed video %s: %s", video.id, exc)


if __name__ == "__main__":
    run_worker()
