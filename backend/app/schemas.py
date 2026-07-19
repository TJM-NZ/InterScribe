import uuid

from pydantic import BaseModel

from app.models.phase1 import CorrectionEntityType, ReasonCategory
from app.models.video import SpeakerRole


class CorrectionRequest(BaseModel):
    entity_type: CorrectionEntityType
    entity_id: uuid.UUID
    field_name: str | None = None
    original_value: dict | None = None
    corrected_value: dict | None = None
    reason_category: ReasonCategory
    reason_note: str | None = None


class SpeakerAssignment(BaseModel):
    speaker_label: str
    role: SpeakerRole


class SpeakerAssignmentsRequest(BaseModel):
    assignments: list[SpeakerAssignment]
