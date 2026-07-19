"""Add headline_text to quotes

Revision ID: 009
Revises: 008
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column("headline_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quotes", "headline_text")
