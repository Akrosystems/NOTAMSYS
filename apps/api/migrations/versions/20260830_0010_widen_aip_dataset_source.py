"""Widen aip_datasets.source to String(300).

Revision ID: 20260830_0010
Revises: 20260830_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0010"
down_revision: str | None = "20260830_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "aip_datasets",
        "source",
        existing_type=sa.String(40),
        type_=sa.String(300),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "aip_datasets",
        "source",
        existing_type=sa.String(300),
        type_=sa.String(40),
        existing_nullable=False,
    )
