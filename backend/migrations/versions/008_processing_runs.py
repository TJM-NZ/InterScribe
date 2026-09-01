"""Add processing_runs table for per-phase timing

Revision ID: 008
Revises: 007
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wall_seconds", sa.Float(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_runs_video_id", "processing_runs", ["video_id"])
    op.create_index("ix_processing_runs_phase", "processing_runs", ["phase"])


def downgrade() -> None:
    op.drop_index("ix_processing_runs_phase", table_name="processing_runs")
    op.drop_index("ix_processing_runs_video_id", table_name="processing_runs")
    op.drop_table("processing_runs")
