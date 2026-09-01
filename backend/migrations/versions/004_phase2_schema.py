"""Phase 2 schema — phase2_chunks, quote_candidates, quotes

Revision ID: 004
Revises: 003
Create Date: 2026-07-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phase2_chunks",
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
        "quote_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phase2_chunk_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(), nullable=False),
        sa.Column("narrative_alignment_score", sa.Float(), nullable=False),
        sa.Column("is_notable_moment", sa.Boolean(), nullable=False),
        sa.Column("notable_moment_id", sa.UUID(), nullable=True),
        sa.Column("raw_qwen_output", sa.JSON(), nullable=False),
        sa.Column("discarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("discard_reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["phase2_chunk_id"], ["phase2_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notable_moment_id"], ["notable_moments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "quotes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("start_ts", sa.Float(), nullable=False),
        sa.Column("end_ts", sa.Float(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("speaker_label", sa.String(), nullable=False),
        sa.Column("narrative_alignment_score", sa.Float(), nullable=False),
        sa.Column("is_notable_moment", sa.Boolean(), nullable=False),
        sa.Column("notable_moment_id", sa.UUID(), nullable=True),
        sa.Column("source_candidate_ids", sa.JSON(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notable_moment_id"], ["notable_moments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("quotes")
    op.drop_table("quote_candidates")
    op.drop_table("phase2_chunks")
