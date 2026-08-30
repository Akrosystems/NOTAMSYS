"""Add qcode_corrections feedback log table.

Revision ID: 20260830_0009
Revises: 20260818_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qcode_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("officer_id", sa.Uuid(), nullable=False),
        sa.Column("location_indicator", sa.String(8), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("suggested_q_code", sa.String(8), nullable=True),
        sa.Column("suggested_confidence", sa.Integer(), nullable=True),
        sa.Column("chosen_q_code", sa.String(8), nullable=False),
        sa.Column("suggestion_was_in_top5", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["officer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["notam_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qcode_corrections_chosen_q_code", "qcode_corrections", ["chosen_q_code"])
    op.create_index("ix_qcode_corrections_officer_id", "qcode_corrections", ["officer_id"])
    op.create_index("ix_qcode_corrections_request_id", "qcode_corrections", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_qcode_corrections_request_id", table_name="qcode_corrections")
    op.drop_index("ix_qcode_corrections_officer_id", table_name="qcode_corrections")
    op.drop_index("ix_qcode_corrections_chosen_q_code", table_name="qcode_corrections")
    op.drop_table("qcode_corrections")
