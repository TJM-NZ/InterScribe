import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import api_error, get_video_or_404
from app.models.phase1 import (
    Correction,
    CorrectionEntityType,
    CorrectionStage,
    NarrativeCluster,
    NotableMoment,
    ReasonCategory,
)
from app.models.video import JobStatus, PHASE1_VIEWABLE_STATUSES, Video
from app.schemas import CorrectionRequest

router = APIRouter()


@router.get("/api/videos/{video_id}/phase1/narrative")
def get_phase1_narrative(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status not in PHASE1_VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 1 narrative not yet available", "PHASE1_NOT_READY"),
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


@router.post("/api/videos/{video_id}/phase1/corrections")
def log_correction(
    video_id: uuid.UUID,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
):
    video = get_video_or_404(video_id, db)

    # Two-step check: give the frontend a distinct code when the user double-submits
    # a correction after already confirming review (PHASE1_ALREADY_REVIEWED), vs
    # when the video simply isn't at the right stage yet (PHASE1_NOT_READY).
    if video.status == JobStatus.phase1_reviewed:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 1 review already confirmed", "PHASE1_ALREADY_REVIEWED"),
        )

    if video.status != JobStatus.phase1_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 1 not ready for review", "PHASE1_NOT_READY"),
        )

    # Validate entity belongs to this video
    if body.entity_type == CorrectionEntityType.narrative_cluster:
        entity = db.get(NarrativeCluster, body.entity_id)
        if not entity or entity.video_id != video_id:
            raise HTTPException(
                status_code=400,
                detail=api_error("entity_id does not belong to this video", "INVALID_ENTITY"),
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
                detail=api_error("entity_id does not belong to this video", "INVALID_ENTITY"),
            )
        # Mark as reviewed on any action
        entity.reviewed = True
        # Apply edit to description if present
        if body.field_name == "description" and body.corrected_value is not None:
            new_desc = body.corrected_value.get("description")
            if new_desc:
                entity.description = str(new_desc)
    elif body.entity_type == CorrectionEntityType.quote:
        # quote corrections belong to the Phase 2 endpoint (C8)
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "Quote corrections must be submitted to POST /phase2/corrections",
                "WRONG_STAGE",
            ),
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=api_error("Invalid entity_type", "INVALID_ENTITY_TYPE"),
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



@router.post("/api/videos/{video_id}/phase1/confirm-review")
def confirm_phase1_review(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status != JobStatus.phase1_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Video not at phase1_ready_for_review", "PHASE1_NOT_READY"),
        )

    # D4 (SPEC-003): auto-enqueue Phase 2 immediately after phase1 confirm-review
    video.status = JobStatus.phase2_queued
    db.commit()

    return {"video_id": str(video_id), "status": "phase1_reviewed"}
