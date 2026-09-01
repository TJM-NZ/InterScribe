import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.video import Video


def api_error(msg: str, code: str, trace_id: uuid.UUID | None = None) -> dict:
    return {"error": msg, "code": code, "trace_id": str(trace_id or uuid.uuid4())}


def get_video_or_404(video_id: uuid.UUID, db: Session) -> Video:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=api_error("Video not found", "NOT_FOUND"))
    return video
