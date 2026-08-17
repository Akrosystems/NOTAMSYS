"""Add Notam.aixm_xml (real AIXM 5.1.1 Event XML).

Revision ID: 20260815_0004
Revises: 20260815_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0004"
down_revision: str | None = "20260815_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notams", sa.Column("aixm_xml", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notams", "aixm_xml")
