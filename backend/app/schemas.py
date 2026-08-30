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


class TranscriptCorrectionRequest(BaseModel):
    segment_id: uuid.UUID
    corrected_text: str
    reason_category: ReasonCategory
    reason_note: str | None = None


class TranscriptSpeakerCorrectionRequest(BaseModel):
    segment_id: uuid.UUID
    corrected_speaker_label: str
    reason_category: ReasonCategory
    reason_note: str | None = None


class TranscriptMergeRequest(BaseModel):
    segment_id: uuid.UUID


class SpeakerAssignment(BaseModel):
    speaker_label: str
    role: SpeakerRole
    name: str | None = None


class SpeakerAssignmentsRequest(BaseModel):
    assignments: list[SpeakerAssignment]
