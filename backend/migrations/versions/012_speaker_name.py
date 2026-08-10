"""Add name to speaker_role_maps

Revision ID: 012
Revises: 011
Create Date: 2026-08-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "speaker_role_maps",
        sa.Column("name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("speaker_role_maps", "name")
