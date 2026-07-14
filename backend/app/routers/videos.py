import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.video import JobStatus, SpeakerRole, SpeakerRoleMap, TranscriptSegment, Video
from app.services.storage import (
    DurationExceededError,
    FileTooLargeError,
    UnsupportedMediaError,
    store_upload,
)

router = APIRouter()


def _error(msg: str, code: str, trace_id: uuid.UUID | None = None) -> dict:
    return {
        "error": msg,
        "code": code,
        "trace_id": str(trace_id or uuid.uuid4()),
    }


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/api/videos", status_code=201)
def upload_video(file: UploadFile, db: Session = Depends(get_db)):
    try:
        storage_path, media_type_val, duration = store_upload(file.file, file.filename or "upload")
    except UnsupportedMediaError as exc:
        raise HTTPException(status_code=400, detail=_error(str(exc), "UNSUPPORTED_MEDIA_TYPE"))
    except (FileTooLargeError, DurationExceededError) as exc:
        raise HTTPException(status_code=413, detail=_error(str(exc), "FILE_TOO_LARGE"))

    video = Video(
        original_filename=file.filename or "upload",
        storage_path=storage_path,
        media_type=media_type_val,
        duration_seconds=duration,
        status=JobStatus.uploaded,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

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
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=_error("Video not found", "NOT_FOUND"))
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
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=_error("Video not found", "NOT_FOUND"))

    reviewable = {JobStatus.ready_for_review, JobStatus.reviewed}
    if video.status not in reviewable:
        raise HTTPException(
            status_code=409,
            detail=_error("Transcript not yet available", "TRANSCRIPT_NOT_READY"),
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
            }
            for s in segments
        ]
    }


class SpeakerAssignment(BaseModel):
    speaker_label: str
    role: SpeakerRole


class SpeakerAssignmentsRequest(BaseModel):
    assignments: list[SpeakerAssignment]


@router.patch("/api/videos/{video_id}/speakers")
def assign_speakers(
    video_id: uuid.UUID,
    body: SpeakerAssignmentsRequest,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=_error("Video not found", "NOT_FOUND"))

    reviewable = {JobStatus.ready_for_review, JobStatus.reviewed}
    if video.status not in reviewable:
        raise HTTPException(
            status_code=409,
            detail=_error("Video not ready for review", "NOT_READY_FOR_REVIEW"),
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
                detail=_error(
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
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=_error("Video not found", "NOT_FOUND"))

    if video.status != JobStatus.ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=_error("Video not ready for review", "NOT_READY_FOR_REVIEW"),
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
            detail=_error(
                "Not all speakers have been assigned a role",
                "SPEAKERS_UNMAPPED",
            ),
        )

    video.status = JobStatus.reviewed
    db.commit()

    return {"video_id": str(video_id), "status": video.status}
