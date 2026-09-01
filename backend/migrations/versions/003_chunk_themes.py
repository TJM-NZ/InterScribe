"""Add chunk_themes table and theme_id to notable_moments

Revision ID: 003
Revises: 002
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_themes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("theme_index", sa.Integer(), nullable=False),
        sa.Column("topic_focus", sa.Text(), nullable=False),
        sa.Column("topic_tags", sa.JSON(), nullable=False),
        sa.Column("start_segment_id", sa.Integer(), nullable=False),
        sa.Column("end_segment_id", sa.Integer(), nullable=False),
        sa.Column("theme_embedding", Vector(384), nullable=False),
        sa.Column("cluster_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["chunk_id"], ["transcript_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["narrative_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "notable_moments",
        sa.Column("theme_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notable_moments_theme_id",
        "notable_moments",
        "chunk_themes",
        ["theme_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notable_moments_theme_id", "notable_moments", type_="foreignkey")
    op.drop_column("notable_moments", "theme_id")
    op.drop_table("chunk_themes")
