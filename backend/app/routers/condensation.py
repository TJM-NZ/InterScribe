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
)
from app.models.phase2 import Quote
from app.models.video import CONDENSATION_VIEWABLE_STATUSES, JobStatus
from app.schemas import CorrectionRequest

router = APIRouter()


@router.get("/api/videos/{video_id}/condensation/headlines")
def get_condensation_headlines(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status not in CONDENSATION_VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error("Condensation not yet available", "CONDENSATION_NOT_READY"),
        )

    quotes = (
        db.execute(
            select(Quote)
            .where(Quote.video_id == video_id)
            .where(Quote.quote_type == "headline")
            .order_by(Quote.narrative_alignment_score.desc())
        )
        .scalars()
        .all()
    )

    return {
        "quotes": [
            {
                "id": str(q.id),
                "video_id": str(q.video_id),
                "start_segment_id": q.start_segment_id,
                "end_segment_id": q.end_segment_id,
                "start_ts": q.start_ts,
                "end_ts": q.end_ts,
                "quote_text": q.quote_text,
                "headline_text": q.headline_text,
                "speaker_label": q.speaker_label,
                "quote_type": q.quote_type,
                "narrative_alignment_score": q.narrative_alignment_score,
                "is_notable_moment": q.is_notable_moment,
                "notable_moment_id": str(q.notable_moment_id) if q.notable_moment_id else None,
                "source_candidate_ids": q.source_candidate_ids,
                "reviewed": q.reviewed,
            }
            for q in quotes
        ]
    }


@router.post("/api/videos/{video_id}/condensation/corrections")
def log_condensation_correction(
    video_id: uuid.UUID,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
):
    video = get_video_or_404(video_id, db)

    if video.status == JobStatus.condensation_reviewed:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "Condensation review already confirmed", "CONDENSATION_ALREADY_REVIEWED"
            ),
        )

    if video.status != JobStatus.condensation_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Condensation not ready for review", "CONDENSATION_NOT_READY"),
        )

    if body.entity_type != CorrectionEntityType.headline_condensation:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "Condensation corrections only accept entity_type 'headline_condensation'",
                "INVALID_ENTITY_TYPE",
            ),
        )

    quote = db.get(Quote, body.entity_id)
    if not quote or quote.video_id != video_id or quote.quote_type != "headline":
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "entity_id does not belong to this video or is not a headline quote",
                "INVALID_ENTITY",
            ),
        )

    if body.field_name == "headline_text":
        new_text = (
            body.corrected_value.get("headline_text")
            if isinstance(body.corrected_value, dict)
            else None
        )
        quote.headline_text = new_text
    elif body.field_name == "quote_type":
        quote.quote_type = "substantive"
        quote.headline_text = None

    correction = Correction(
        video_id=video_id,
        stage=CorrectionStage.condensation,
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


@router.post("/api/videos/{video_id}/condensation/confirm-review")
def confirm_condensation_review(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status != JobStatus.condensation_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "Video not at condensation_ready_for_review", "CONDENSATION_NOT_READY"
            ),
        )

    video.status = JobStatus.condensation_reviewed
    db.commit()

    return {"video_id": str(video_id), "status": "condensation_reviewed"}
