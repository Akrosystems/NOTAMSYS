"""Add org_settings (admin-editable platform branding).

Revision ID: 20260817_0006
Revises: 20260817_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0006"
down_revision: str | None = "20260817_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_name", sa.String(length=80), nullable=False),
        sa.Column("org_subtitle", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_object_key", sa.String(length=255), nullable=True),
        sa.Column("logo_media_type", sa.String(length=100), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("org_settings")
