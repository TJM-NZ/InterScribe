import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UUID


class Phase2Chunk(Base):
    __tablename__ = "phase2_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)


class QuoteCandidate(Base):
    __tablename__ = "quote_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phase2_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phase2_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    narrative_alignment_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_notable_moment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notable_moment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notable_moments.id", ondelete="SET NULL"), nullable=True
    )
    quote_type: Mapped[str] = mapped_column(String, nullable=False, default="substantive", server_default="substantive")
    raw_qwen_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    discarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discard_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, nullable=False)
    end_ts: Mapped[float] = mapped_column(Float, nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    narrative_alignment_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_notable_moment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notable_moment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notable_moments.id", ondelete="SET NULL"), nullable=True
    )
    # JSONB array of QuoteCandidate UUIDs — audit trail, not a relational FK (SPEC-003)
    source_candidate_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    quote_type: Mapped[str] = mapped_column(String, nullable=False, default="substantive", server_default="substantive")
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    headline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
