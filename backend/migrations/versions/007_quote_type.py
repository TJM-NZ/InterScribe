"""Add quote_type to quote_candidates and quotes

Revision ID: 007
Revises: 006
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_candidates",
        sa.Column("quote_type", sa.String(), nullable=False, server_default="substantive"),
    )
    op.add_column(
        "quotes",
        sa.Column("quote_type", sa.String(), nullable=False, server_default="substantive"),
    )


def downgrade() -> None:
    op.drop_column("quote_candidates", "quote_type")
    op.drop_column("quotes", "quote_type")
