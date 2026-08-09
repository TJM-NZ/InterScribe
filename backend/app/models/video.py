import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UUID


class MediaType(str, PyEnum):
    video = "video"
    audio = "audio"


class JobStatus(str, PyEnum):
    uploaded = "uploaded"
    queued = "queued"
    transcribing = "transcribing"
    ready_for_review = "ready_for_review"
    phase1_queued = "phase1_queued"
    phase1_processing = "phase1_processing"
    phase1_ready_for_review = "phase1_ready_for_review"
    phase1_reviewed = "phase1_reviewed"
    phase2_queued = "phase2_queued"
    phase2_processing = "phase2_processing"
    phase2_ready_for_review = "phase2_ready_for_review"
    phase2_reviewed = "phase2_reviewed"
    condensation_queued = "condensation_queued"
    condensation_processing = "condensation_processing"
    condensation_ready_for_review = "condensation_ready_for_review"
    condensation_reviewed = "condensation_reviewed"
    failed = "failed"


# Named status sets — state-machine semantics shared across routers
TRANSCRIPT_VIEWABLE_STATUSES = frozenset({
    JobStatus.ready_for_review,
    JobStatus.phase1_queued, JobStatus.phase1_processing,
    JobStatus.phase1_ready_for_review, JobStatus.phase1_reviewed,
    JobStatus.phase2_queued, JobStatus.phase2_processing,
    JobStatus.phase2_ready_for_review, JobStatus.phase2_reviewed,
    JobStatus.condensation_queued, JobStatus.condensation_processing,
    JobStatus.condensation_ready_for_review, JobStatus.condensation_reviewed,
})
SPEAKER_REVIEW_STATUSES = frozenset({JobStatus.ready_for_review})
PHASE1_VIEWABLE_STATUSES = frozenset({
    JobStatus.phase1_ready_for_review, JobStatus.phase1_reviewed,
    JobStatus.phase2_queued, JobStatus.phase2_processing,
    JobStatus.phase2_ready_for_review, JobStatus.phase2_reviewed,
    JobStatus.condensation_queued, JobStatus.condensation_processing,
    JobStatus.condensation_ready_for_review, JobStatus.condensation_reviewed,
})
PHASE2_VIEWABLE_STATUSES = frozenset({
    JobStatus.phase2_ready_for_review, JobStatus.phase2_reviewed,
    JobStatus.condensation_queued, JobStatus.condensation_processing,
    JobStatus.condensation_ready_for_review, JobStatus.condensation_reviewed,
})
CONDENSATION_VIEWABLE_STATUSES = frozenset({
    JobStatus.condensation_ready_for_review, JobStatus.condensation_reviewed,
})


class ProcessingPhase(str, PyEnum):
    transcription = "transcription"
    phase1 = "phase1"
    phase2 = "phase2"
    condensation = "condensation"


class SpeakerRole(str, PyEnum):
    interviewer = "interviewer"
    interviewee = "interviewee"
    unknown = "unknown"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[MediaType] = mapped_column(String, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[JobStatus] = mapped_column(String, nullable=False, default=JobStatus.uploaded)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alignment_skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uploaded_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    speaker_role_map: Mapped[list["SpeakerRoleMap"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    processing_runs: Mapped[list["ProcessingRun"]] = relationship(
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


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[ProcessingPhase] = mapped_column(String, nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wall_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    succeeded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_processing_runs_video_id", "video_id"),
        Index("ix_processing_runs_phase", "phase"),
    )

    video: Mapped["Video"] = relationship(back_populates="processing_runs")
