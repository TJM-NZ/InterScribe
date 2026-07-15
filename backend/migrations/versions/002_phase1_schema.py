"""Phase 1 schema — turns, chunks, narratives, clusters, notable moments, corrections

Revision ID: 002
Revises: 001
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "transcript_turns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("combined_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "transcript_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "narrative_clusters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("representative_label", sa.Text(), nullable=False),
        sa.Column("cluster_size", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "chunk_narratives",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("tone", sa.String(), nullable=False),
        sa.Column("topic_tags", sa.JSON(), nullable=False),
        sa.Column("narrative_embedding", Vector(384), nullable=False),
        sa.Column("cluster_id", sa.UUID(), nullable=True),
        sa.Column("raw_qwen_output", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["transcript_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["narrative_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notable_moments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["chunk_id"], ["transcript_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "corrections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("original_value", sa.JSON(), nullable=True),
        sa.Column("corrected_value", sa.JSON(), nullable=True),
        sa.Column("reason_category", sa.String(), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("corrections")
    op.drop_table("notable_moments")
    op.drop_table("chunk_narratives")
    op.drop_table("narrative_clusters")
    op.drop_table("transcript_chunks")
    op.drop_table("transcript_turns")
