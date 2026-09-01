"""Drop unused narrative_embedding from chunk_narratives

Revision ID: 010
Revises: 009
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("chunk_narratives", "narrative_embedding")


def downgrade() -> None:
    op.add_column(
        "chunk_narratives",
        sa.Column("narrative_embedding", Vector(384), nullable=True),
    )
