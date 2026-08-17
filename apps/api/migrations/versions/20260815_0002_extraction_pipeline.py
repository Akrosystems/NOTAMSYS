"""Add extraction pipeline tables.

Revision ID: 20260815_0002
Revises: 20260815_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0002"
down_revision: str | None = "20260815_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("engine", sa.String(length=40), nullable=False),
        sa.Column("engine_version", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "SUCCEEDED", "FAILED", name="extraction_status"),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name=op.f("fk_extraction_runs_attachment_id_attachments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_runs")),
    )
    op.create_index(
        op.f("ix_extraction_runs_attachment_id"),
        "extraction_runs",
        ["attachment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extraction_runs_created_at"), "extraction_runs", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_extraction_runs_status"), "extraction_runs", ["status"], unique=False
    )

    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column(
            "extractor", sa.Enum("REGEX", "GRAMMAR", "MODEL", name="extractor_kind"), nullable=False
        ),
        sa.Column("accepted_by_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["accepted_by_id"], ["users.id"], name=op.f("fk_extracted_fields_accepted_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["extraction_runs.id"],
            name=op.f("fk_extracted_fields_run_id_extraction_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_fields")),
    )
    op.create_index(
        op.f("ix_extracted_fields_run_id"), "extracted_fields", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_extracted_fields_run_id"), table_name="extracted_fields")
    op.drop_table("extracted_fields")
    op.drop_index(op.f("ix_extraction_runs_status"), table_name="extraction_runs")
    op.drop_index(op.f("ix_extraction_runs_created_at"), table_name="extraction_runs")
    op.drop_index(op.f("ix_extraction_runs_attachment_id"), table_name="extraction_runs")
    op.drop_table("extraction_runs")
