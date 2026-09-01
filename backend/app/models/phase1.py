<<<<<<< Updated upstream
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UUID


class CorrectionStage(str, PyEnum):
    transcription = "transcription"
    phase1 = "phase1"
    phase2 = "phase2"
    condensation = "condensation"


class CorrectionEntityType(str, PyEnum):
    transcript_segment = "transcript_segment"
    narrative_cluster = "narrative_cluster"
    notable_moment = "notable_moment"
    quote = "quote"
    headline_condensation = "headline_condensation"


class ReasonCategory(str, PyEnum):
    model_error = "model_error"
    ambiguous_input = "ambiguous_input"
    edge_case = "edge_case"
    preference = "preference"


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    combined_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    narrative: Mapped["ChunkNarrative | None"] = relationship(back_populates="chunk", uselist=False)
    themes: Mapped[list["ChunkTheme"]] = relationship(back_populates="chunk")
    notable_moments: Mapped[list["NotableMoment"]] = relationship(back_populates="chunk")


class NarrativeCluster(Base):
    __tablename__ = "narrative_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    representative_label: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_size: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    themes: Mapped[list["ChunkTheme"]] = relationship(back_populates="cluster")


class ChunkNarrative(Base):
    __tablename__ = "chunk_narratives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String, nullable=False)
    tone: Mapped[str] = mapped_column(String, nullable=False)
    topic_tags: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_qwen_output: Mapped[dict] = mapped_column(JSONB, nullable=False)

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="narrative")


class ChunkTheme(Base):
    __tablename__ = "chunk_themes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    theme_index: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_focus: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tags: Mapped[dict] = mapped_column(JSONB, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    theme_embedding = mapped_column(Vector(384), nullable=False)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_clusters.id"), nullable=True
    )

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="themes")
    cluster: Mapped["NarrativeCluster | None"] = relationship(back_populates="themes")


class NotableMoment(Base):
    __tablename__ = "notable_moments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunk_themes.id", ondelete="SET NULL"), nullable=True
    )
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="notable_moments")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[CorrectionStage] = mapped_column(String, nullable=False)
    entity_type: Mapped[CorrectionEntityType] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    original_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    corrected_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason_category: Mapped[ReasonCategory] = mapped_column(String, nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )
=======
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UUID


class CorrectionStage(str, PyEnum):
    phase1 = "phase1"
    phase2 = "phase2"
    condensation = "condensation"


class CorrectionEntityType(str, PyEnum):
    narrative_cluster = "narrative_cluster"
    notable_moment = "notable_moment"
    quote = "quote"
    headline_condensation = "headline_condensation"


class ReasonCategory(str, PyEnum):
    model_error = "model_error"
    ambiguous_input = "ambiguous_input"
    edge_case = "edge_case"
    preference = "preference"


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    combined_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    narrative: Mapped["ChunkNarrative | None"] = relationship(back_populates="chunk", uselist=False)
    themes: Mapped[list["ChunkTheme"]] = relationship(back_populates="chunk")
    notable_moments: Mapped[list["NotableMoment"]] = relationship(back_populates="chunk")


class NarrativeCluster(Base):
    __tablename__ = "narrative_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    representative_label: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_size: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    themes: Mapped[list["ChunkTheme"]] = relationship(back_populates="cluster")


class ChunkNarrative(Base):
    __tablename__ = "chunk_narratives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String, nullable=False)
    tone: Mapped[str] = mapped_column(String, nullable=False)
    topic_tags: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_qwen_output: Mapped[dict] = mapped_column(JSONB, nullable=False)

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="narrative")


class ChunkTheme(Base):
    __tablename__ = "chunk_themes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    theme_index: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_focus: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tags: Mapped[dict] = mapped_column(JSONB, nullable=False)
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    theme_embedding = mapped_column(Vector(384), nullable=False)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_clusters.id"), nullable=True
    )

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="themes")
    cluster: Mapped["NarrativeCluster | None"] = relationship(back_populates="themes")


class NotableMoment(Base):
    __tablename__ = "notable_moments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunk_themes.id", ondelete="SET NULL"), nullable=True
    )
    start_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    end_segment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    chunk: Mapped["TranscriptChunk"] = relationship(back_populates="notable_moments")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[CorrectionStage] = mapped_column(String, nullable=False)
    entity_type: Mapped[CorrectionEntityType] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    original_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    corrected_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason_category: Mapped[ReasonCategory] = mapped_column(String, nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )
>>>>>>> Stashed changes
