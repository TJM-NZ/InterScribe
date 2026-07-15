import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.phase1 import (
    ChunkNarrative,
    Correction,
    CorrectionEntityType,
    CorrectionStage,
    NarrativeCluster,
    NotableMoment,
    ReasonCategory,
)
from app.models.video import JobStatus, Video

router = APIRouter()


def _error(msg: str, code: str, trace_id: uuid.UUID | None = None) -> dict:
    return {"error": msg, "code": code, "trace_id": str(trace_id or uuid.uuid4())}


def _get_video_or_404(video_id: uuid.UUID, db: Session) -> Video:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=_error("Video not found", "NOT_FOUND"))
    return video


@router.get("/api/videos/{video_id}/phase1/narrative")
def get_phase1_narrative(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = _get_video_or_404(video_id, db)

    reviewable = {JobStatus.phase1_ready_for_review, JobStatus.phase1_reviewed}
    if video.status not in reviewable:
        raise HTTPException(
            status_code=409,
            detail=_error("Phase 1 narrative not yet available", "PHASE1_NOT_READY"),
        )

    clusters = (
        db.execute(
            select(NarrativeCluster)
            .where(NarrativeCluster.video_id == video_id)
            .order_by(NarrativeCluster.rank)
        )
        .scalars()
        .all()
    )

    moments = (
        db.execute(
            select(NotableMoment)
            .where(NotableMoment.video_id == video_id)
            .order_by(NotableMoment.start_segment_id)
        )
        .scalars()
        .all()
    )

    narratives = (
        db.execute(
            select(ChunkNarrative).where(ChunkNarrative.video_id == video_id)
        )
        .scalars()
        .all()
    )
    narrative_map = {str(n.chunk_id): n for n in narratives}

    return {
        "clusters": [
            {
                "id": str(c.id),
                "video_id": str(c.video_id),
                "representative_label": c.representative_label,
                "cluster_size": c.cluster_size,
                "rank": c.rank,
            }
            for c in clusters
        ],
        "notable_moments": [
            {
                "id": str(m.id),
                "video_id": str(m.video_id),
                "chunk_id": str(m.chunk_id),
                "start_segment_id": m.start_segment_id,
                "end_segment_id": m.end_segment_id,
                "description": m.description,
                "reviewed": m.reviewed,
            }
            for m in moments
        ],
    }


class CorrectionRequest(BaseModel):
    entity_type: CorrectionEntityType
    entity_id: uuid.UUID
    field_name: str | None = None
    original_value: dict | None = None
    corrected_value: dict | None = None
    reason_category: ReasonCategory
    reason_note: str | None = None


@router.post("/api/videos/{video_id}/phase1/corrections")
def log_correction(
    video_id: uuid.UUID,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
):
    video = _get_video_or_404(video_id, db)

    if video.status == JobStatus.phase1_reviewed:
        raise HTTPException(
            status_code=409,
            detail=_error("Phase 1 review already confirmed", "PHASE1_ALREADY_REVIEWED"),
        )

    reviewable = {JobStatus.phase1_ready_for_review}
    if video.status not in reviewable:
        raise HTTPException(
            status_code=409,
            detail=_error("Phase 1 not ready for review", "PHASE1_NOT_READY"),
        )

    # Validate entity belongs to this video
    if body.entity_type == CorrectionEntityType.narrative_cluster:
        entity = db.get(NarrativeCluster, body.entity_id)
        if not entity or entity.video_id != video_id:
            raise HTTPException(
                status_code=400,
                detail=_error("entity_id does not belong to this video", "INVALID_ENTITY"),
            )
        # Apply edit if it's a field correction on representative_label
        if body.field_name == "representative_label" and body.corrected_value is not None:
            new_label = body.corrected_value.get("representative_label")
            if new_label:
                entity.representative_label = str(new_label)
    elif body.entity_type == CorrectionEntityType.notable_moment:
        entity = db.get(NotableMoment, body.entity_id)
        if not entity or entity.video_id != video_id:
            raise HTTPException(
                status_code=400,
                detail=_error("entity_id does not belong to this video", "INVALID_ENTITY"),
            )
        # Mark as reviewed on any action
        entity.reviewed = True
        # Apply edit to description if present
        if body.field_name == "description" and body.corrected_value is not None:
            new_desc = body.corrected_value.get("description")
            if new_desc:
                entity.description = str(new_desc)
    else:
        raise HTTPException(
            status_code=400,
            detail=_error("Invalid entity_type", "INVALID_ENTITY_TYPE"),
        )

    correction = Correction(
        video_id=video_id,
        stage=CorrectionStage.phase1,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        field_name=body.field_name,
        original_value=body.original_value,
        corrected_value=body.corrected_value,
        reason_category=body.reason_category,
        reason_note=body.reason_note,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)

    return {"correction_id": str(correction.id)}


@router.post("/api/videos/{video_id}/phase1/enqueue")
def enqueue_phase1(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = _get_video_or_404(video_id, db)

    if video.status != JobStatus.reviewed:
        raise HTTPException(
            status_code=409,
            detail=_error("Video must be in 'reviewed' status to enqueue Phase 1", "INVALID_STATUS"),
        )

    video.status = JobStatus.phase1_queued
    db.commit()

    return {"video_id": str(video_id), "status": "phase1_queued"}


@router.post("/api/videos/{video_id}/phase1/confirm-review")
def confirm_phase1_review(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = _get_video_or_404(video_id, db)

    if video.status != JobStatus.phase1_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=_error("Video not at phase1_ready_for_review", "PHASE1_NOT_READY"),
        )

    video.status = JobStatus.phase1_reviewed
    db.commit()

    return {"video_id": str(video_id), "status": "phase1_reviewed"}
