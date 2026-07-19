import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import api_error, get_video_or_404
from app.schemas import SpeakerAssignment, SpeakerAssignmentsRequest
from app.models.phase1 import NarrativeCluster, TranscriptChunk, TranscriptTurn
from app.models.phase2 import Phase2Chunk, Quote
from app.models.video import (
    JobStatus,
    ProcessingPhase,
    ProcessingRun,
    SPEAKER_REVIEW_STATUSES,
    TRANSCRIPT_VIEWABLE_STATUSES,
    SpeakerRoleMap,
    TranscriptSegment,
    Video,
)
from app.services.storage import (
    DurationExceededError,
    FileTooLargeError,
    UnsupportedMediaError,
    store_upload,
)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/videos")
def list_videos(db: Session = Depends(get_db)):
    videos = (
        db.execute(select(Video).order_by(Video.uploaded_at.desc()))
        .scalars()
        .all()
    )
    return {
        "videos": [
            {
                "id": str(v.id),
                "status": v.status,
                "error_reason": v.error_reason,
                "duration_seconds": v.duration_seconds,
                "original_filename": v.original_filename,
                "media_type": v.media_type,
                "uploaded_at": v.uploaded_at.isoformat(),
            }
            for v in videos
        ]
    }


@router.post("/api/videos", status_code=201)
def upload_video(file: UploadFile, db: Session = Depends(get_db)):
    try:
        storage_path, media_type_val, duration = store_upload(file.file, file.filename or "upload")
    except UnsupportedMediaError as exc:
        raise HTTPException(status_code=400, detail=api_error(str(exc), "UNSUPPORTED_MEDIA_TYPE"))
    except (FileTooLargeError, DurationExceededError) as exc:
        raise HTTPException(status_code=413, detail=api_error(str(exc), "FILE_TOO_LARGE"))

    video = Video(
        original_filename=file.filename or "upload",
        storage_path=storage_path,
        media_type=media_type_val,
        duration_seconds=duration,
        status=JobStatus.uploaded,
    )
    db.add(video)
    db.flush()

    response = {
        "id": str(video.id),
        "status": "uploaded",
        "original_filename": video.original_filename,
        "media_type": video.media_type,
    }

    video.status = JobStatus.queued
    db.commit()

    return response


@router.get("/api/videos/{video_id}")
def get_video(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)
    return {
        "id": str(video.id),
        "status": video.status,
        "error_reason": video.error_reason,
        "duration_seconds": video.duration_seconds,
        "original_filename": video.original_filename,
        "media_type": video.media_type,
        "uploaded_at": video.uploaded_at.isoformat(),
    }


@router.get("/api/videos/{video_id}/transcript")
def get_transcript(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status not in TRANSCRIPT_VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error("Transcript not yet available", "TRANSCRIPT_NOT_READY"),
        )

    segments = (
        db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.video_id == video_id)
            .order_by(TranscriptSegment.segment_id)
        )
        .scalars()
        .all()
    )
    return {
        "segments": [
            {
                "id": str(s.id),
                "video_id": str(s.video_id),
                "segment_id": s.segment_id,
                "start_ts": s.start_ts,
                "end_ts": s.end_ts,
                "text": s.text,
                "speaker_label": s.speaker_label,
                "confidence": s.confidence,
                "repetition_flagged": s.repetition_flagged,
            }
            for s in segments
        ]
    }


@router.patch("/api/videos/{video_id}/speakers")
def assign_speakers(
    video_id: uuid.UUID,
    body: SpeakerAssignmentsRequest,
    db: Session = Depends(get_db),
):
    video = get_video_or_404(video_id, db)

    if video.status not in SPEAKER_REVIEW_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error("Video not ready for review", "NOT_READY_FOR_REVIEW"),
        )

    known_labels = {
        row[0]
        for row in db.execute(
            select(TranscriptSegment.speaker_label)
            .where(TranscriptSegment.video_id == video_id)
            .distinct()
        ).all()
    }

    for assignment in body.assignments:
        if assignment.speaker_label not in known_labels:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Unknown speaker_label: {assignment.speaker_label}",
                    "UNKNOWN_SPEAKER_LABEL",
                ),
            )

    for assignment in body.assignments:
        existing = db.execute(
            select(SpeakerRoleMap).where(
                SpeakerRoleMap.video_id == video_id,
                SpeakerRoleMap.speaker_label == assignment.speaker_label,
            )
        ).scalar_one_or_none()

        if existing:
            existing.role = assignment.role
        else:
            db.add(
                SpeakerRoleMap(
                    video_id=video_id,
                    speaker_label=assignment.speaker_label,
                    role=assignment.role,
                )
            )

    db.commit()

    role_map = (
        db.execute(
            select(SpeakerRoleMap).where(SpeakerRoleMap.video_id == video_id)
        )
        .scalars()
        .all()
    )
    return {
        "video_id": str(video_id),
        "speaker_role_map": [
            {"id": str(r.id), "video_id": str(r.video_id), "speaker_label": r.speaker_label, "role": r.role}
            for r in role_map
        ],
    }


@router.post("/api/videos/{video_id}/confirm-review")
def confirm_review(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status != JobStatus.ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Video not ready for review", "NOT_READY_FOR_REVIEW"),
        )

    distinct_labels = {
        row[0]
        for row in db.execute(
            select(TranscriptSegment.speaker_label)
            .where(TranscriptSegment.video_id == video_id)
            .distinct()
        ).all()
    }
    mapped_labels = {
        row[0]
        for row in db.execute(
            select(SpeakerRoleMap.speaker_label)
            .where(SpeakerRoleMap.video_id == video_id)
        ).all()
    }

    if distinct_labels - mapped_labels:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "Not all speakers have been assigned a role",
                "SPEAKERS_UNMAPPED",
            ),
        )

    # D3 (SPEC-002): auto-enqueue Phase 1 immediately after spec-1 confirm
    video.status = JobStatus.phase1_queued
    db.commit()

    return {"video_id": str(video_id), "status": "phase1_queued"}


def _clear_phase1_data(video_id: uuid.UUID, db: Session) -> None:
    db.execute(delete(TranscriptTurn).where(TranscriptTurn.video_id == video_id))
    db.execute(delete(TranscriptChunk).where(TranscriptChunk.video_id == video_id))
    db.execute(delete(NarrativeCluster).where(NarrativeCluster.video_id == video_id))


def _clear_phase2_data(video_id: uuid.UUID, db: Session) -> None:
    db.execute(delete(Phase2Chunk).where(Phase2Chunk.video_id == video_id))
    db.execute(delete(Quote).where(Quote.video_id == video_id))


@router.post("/api/videos/{video_id}/retry")
def retry_video(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status != JobStatus.failed:
        raise HTTPException(
            status_code=409,
            detail=api_error("Video is not in failed status", "NOT_FAILED"),
        )

    has_segments = (
        db.execute(
            select(TranscriptSegment.id).where(TranscriptSegment.video_id == video_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )
    has_clusters = (
        db.execute(
            select(NarrativeCluster.id).where(NarrativeCluster.video_id == video_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )
    has_quotes = (
        db.execute(
            select(Quote.id).where(Quote.video_id == video_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )

    if not has_segments:
        # Transcription failed — no derived data to clean
        video.status = JobStatus.queued
    elif not has_clusters:
        # Phase 1 failed — clean partial phase1 data (intermediate commits may have persisted rows)
        _clear_phase1_data(video_id, db)
        video.status = JobStatus.phase1_queued
    elif not has_quotes:
        # Phase 2 failed — clean partial phase2 data
        _clear_phase2_data(video_id, db)
        video.status = JobStatus.phase2_queued
    else:
        # Condensation failed — quote data is intact; re-queue condensation only
        video.status = JobStatus.condensation_queued

    new_status = video.status
    video.error_reason = None
    db.commit()

    return {"video_id": str(video_id), "status": new_status.value}


_RERUN_STATUSES = {
    JobStatus.phase1_ready_for_review,
    JobStatus.phase1_reviewed,
    JobStatus.phase2_ready_for_review,
    JobStatus.phase2_reviewed,
}

_RERUN_TRANSCRIPT_STATUSES = {
    JobStatus.ready_for_review,
    JobStatus.phase1_ready_for_review,
    JobStatus.phase1_reviewed,
    JobStatus.phase2_ready_for_review,
    JobStatus.phase2_reviewed,
}


@router.post("/api/videos/{video_id}/rerun")
def rerun_video(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status not in _RERUN_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                f"Rerun not allowed from status '{video.status.value}'",
                "INVALID_STATUS",
            ),
        )

    if video.status in (JobStatus.phase2_ready_for_review, JobStatus.phase2_reviewed):
        _clear_phase2_data(video_id, db)
        video.status = JobStatus.phase2_queued
    else:
        # phase1_ready_for_review or phase1_reviewed — clear phase1 + phase2 data
        _clear_phase1_data(video_id, db)
        _clear_phase2_data(video_id, db)
        video.status = JobStatus.phase1_queued

    new_status = video.status
    video.error_reason = None
    db.commit()

    return {"video_id": str(video_id), "status": new_status.value}


@router.post("/api/videos/{video_id}/rerun-transcript")
def rerun_transcript(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status not in _RERUN_TRANSCRIPT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                f"Transcript rerun not allowed from status '{video.status.value}'",
                "INVALID_STATUS",
            ),
        )

    # Clear all derived data in dependency order
    _clear_phase2_data(video_id, db)
    _clear_phase1_data(video_id, db)
    db.execute(delete(SpeakerRoleMap).where(SpeakerRoleMap.video_id == video_id))
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.video_id == video_id))
    video.status = JobStatus.queued
    video.error_reason = None
    db.commit()

    return {"video_id": str(video_id), "status": JobStatus.queued.value}


@router.get("/api/videos/{video_id}/runs")
def get_video_runs(video_id: uuid.UUID, db: Session = Depends(get_db)):
    get_video_or_404(video_id, db)
    runs = db.execute(
        select(ProcessingRun)
        .where(ProcessingRun.video_id == video_id)
        .order_by(ProcessingRun.started_at.asc())
    ).scalars().all()
    return {
        "runs": [
            {
                "id": str(r.id),
                "phase": r.phase,
                "run_number": r.run_number,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "wall_seconds": r.wall_seconds,
                "succeeded": r.succeeded,
                "error_reason": r.error_reason,
            }
            for r in runs
        ]
    }


@router.get("/api/stats/timing")
def get_timing_stats(db: Session = Depends(get_db)):
    stats = {}
    for phase in ProcessingPhase:
        counts = db.execute(
            select(
                func.count().label("run_count"),
                func.count().filter(ProcessingRun.succeeded == True).label("success_count"),
            ).where(ProcessingRun.phase == phase)
        ).one()

        agg = db.execute(
            select(
                func.avg(ProcessingRun.wall_seconds).label("avg_wall_seconds"),
                func.percentile_cont(0.5).within_group(ProcessingRun.wall_seconds.asc()).label("p50"),
                func.percentile_cont(0.95).within_group(ProcessingRun.wall_seconds.asc()).label("p95"),
                func.avg(
                    ProcessingRun.wall_seconds / (Video.duration_seconds / 60.0)
                ).label("avg_wall_per_audio_minute"),
            )
            .join(Video, ProcessingRun.video_id == Video.id)
            .where(
                ProcessingRun.phase == phase,
                ProcessingRun.succeeded == True,
                ProcessingRun.wall_seconds.isnot(None),
                Video.duration_seconds.isnot(None),
                Video.duration_seconds > 0,
            )
        ).one()

        stats[phase.value] = {
            "run_count": counts.run_count,
            "success_count": counts.success_count,
            "avg_wall_seconds": round(agg.avg_wall_seconds, 1) if agg.avg_wall_seconds is not None else None,
            "avg_wall_per_audio_minute": round(agg.avg_wall_per_audio_minute, 2) if agg.avg_wall_per_audio_minute is not None else None,
            "p50_wall_seconds": round(agg.p50, 1) if agg.p50 is not None else None,
            "p95_wall_seconds": round(agg.p95, 1) if agg.p95 is not None else None,
        }
    return stats
