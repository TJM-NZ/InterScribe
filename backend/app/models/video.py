import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UUID(TypeDecorator):
    """UUID that uses native pg UUID in Postgres, String(36) in SQLite."""
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class MediaType(str, PyEnum):
    video = "video"
    audio = "audio"


class JobStatus(str, PyEnum):
    uploaded = "uploaded"
    queued = "queued"
    transcribing = "transcribing"
    ready_for_review = "ready_for_review"
    reviewed = "reviewed"
    phase1_queued = "phase1_queued"
    phase1_processing = "phase1_processing"
    phase1_ready_for_review = "phase1_ready_for_review"
    phase1_reviewed = "phase1_reviewed"
    phase2_queued = "phase2_queued"
    phase2_processing = "phase2_processing"
    phase2_ready_for_review = "phase2_ready_for_review"
    phase2_reviewed = "phase2_reviewed"
    failed = "failed"


class SpeakerRole(str, PyEnum):
    interviewer = "interviewer"
    interviewee = "interviewee"
    unknown = "unknown"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[MediaType] = mapped_column(String, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[JobStatus] = mapped_column(String, nullable=False, default=JobStatus.uploaded)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    speaker_role_map: Mapped[list["SpeakerRoleMap"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, nullable=False)
    end_ts: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    video: Mapped["Video"] = relationship(back_populates="segments")


class SpeakerRoleMap(Base):
    __tablename__ = "speaker_role_maps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[SpeakerRole] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("video_id", "speaker_label", name="uq_video_speaker"),)

    video: Mapped["Video"] = relationship(back_populates="speaker_role_map")
