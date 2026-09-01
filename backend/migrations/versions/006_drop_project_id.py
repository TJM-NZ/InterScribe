"""Drop unused project_id from videos

Revision ID: 006
Revises: 005
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("videos", "project_id")


def downgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("project_id", sa.String(36), nullable=True),
    )
