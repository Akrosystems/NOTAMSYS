"""Widen rule_versions.source_revision to Text.

In practice this column holds a full provenance note (what was
transcribed/verified and when), not a short tag -- SQLite never enforces
VARCHAR(80) so the mismatch went unnoticed until run against real Postgres,
where seeding failed with StringDataRightTruncationError.

Revision ID: 20260817_0005
Revises: 20260815_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0005"
down_revision: str | None = "20260815_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "rule_versions",
        "source_revision",
        existing_type=sa.String(length=80),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "rule_versions",
        "source_revision",
        existing_type=sa.Text(),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
