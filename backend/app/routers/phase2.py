import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import api_error, get_video_or_404
from app.models.phase1 import (
    Correction,
    CorrectionEntityType,
    CorrectionStage,
    ReasonCategory,
)
from app.models.phase2 import Quote
from app.models.video import JobStatus, PHASE2_VIEWABLE_STATUSES, Video
from app.schemas import CorrectionRequest

router = APIRouter()


@router.get("/api/videos/{video_id}/phase2/quotes")
def get_phase2_quotes(
    video_id: uuid.UUID,
    view: str | None = Query(None),
    limit: int | None = Query(None),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    video = get_video_or_404(video_id, db)

    if video.status not in PHASE2_VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 2 quotes not yet available", "PHASE2_NOT_READY"),
        )

    if view not in ("notable", "top"):
        raise HTTPException(
            status_code=400,
            detail=api_error("view must be 'notable' or 'top'", "INVALID_VIEW"),
        )

    q = select(Quote).where(Quote.video_id == video_id)

    if type in ("headline", "substantive"):
        q = q.where(Quote.quote_type == type)

    if view == "notable":
        q = q.where(Quote.is_notable_moment.is_(True)).order_by(Quote.start_segment_id)
    else:
        q = q.order_by(Quote.narrative_alignment_score.desc())
        if limit is not None:
            q = q.limit(limit)

    quotes = db.execute(q).scalars().all()

    return {
        "quotes": [
            {
                "id": str(quote.id),
                "video_id": str(quote.video_id),
                "start_segment_id": quote.start_segment_id,
                "end_segment_id": quote.end_segment_id,
                "start_ts": quote.start_ts,
                "end_ts": quote.end_ts,
                "quote_text": quote.quote_text,
                "speaker_label": quote.speaker_label,
                "quote_type": quote.quote_type,
                "narrative_alignment_score": quote.narrative_alignment_score,
                "is_notable_moment": quote.is_notable_moment,
                "notable_moment_id": str(quote.notable_moment_id) if quote.notable_moment_id else None,
                "source_candidate_ids": quote.source_candidate_ids,
                "reviewed": quote.reviewed,
            }
            for quote in quotes
        ]
    }


@router.post("/api/videos/{video_id}/phase2/corrections")
def log_phase2_correction(
    video_id: uuid.UUID,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
):
    video = get_video_or_404(video_id, db)

    if video.status == JobStatus.phase2_reviewed:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 2 review already confirmed", "PHASE2_ALREADY_REVIEWED"),
        )

    if video.status != JobStatus.phase2_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Phase 2 not ready for review", "PHASE2_NOT_READY"),
        )

    if body.entity_type != CorrectionEntityType.quote:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "Phase 2 corrections only accept entity_type 'quote'",
                "INVALID_ENTITY_TYPE",
            ),
        )

    quote = db.get(Quote, body.entity_id)
    if not quote or quote.video_id != video_id:
        raise HTTPException(
            status_code=400,
            detail=api_error("entity_id does not belong to this video", "INVALID_ENTITY"),
        )

    quote.reviewed = True

    correction = Correction(
        video_id=video_id,
        stage=CorrectionStage.phase2,
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


@router.post("/api/videos/{video_id}/phase2/confirm-review")
def confirm_phase2_review(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = get_video_or_404(video_id, db)

    if video.status != JobStatus.phase2_ready_for_review:
        raise HTTPException(
            status_code=409,
            detail=api_error("Video not at phase2_ready_for_review", "PHASE2_NOT_READY"),
        )

    video.status = JobStatus.condensation_queued
    db.commit()

    return {"video_id": str(video_id), "status": "phase2_reviewed"}
