"""Create the NOTAMSYS schema.

Revision ID: 20260815_0001
Revises:
"""

# Frozen static baseline as of the Phase 0/1 groundwork pass, generated once
# via `alembic revision --autogenerate` against the live models rather than
# `Base.metadata.create_all`/`drop_all`. All schema changes from this point
# forward must be their own incremental migration (`op.add_column` /
# `op.create_table`), not a regenerated snapshot, so `alembic upgrade head`
# stays safe to run against a populated database.

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ORIGINATOR",
                "AIS_OFFICER",
                "AIS_SPECIALIST",
                "NOF_MANAGER",
                "QMS_AUDITOR",
                "SYSTEM_ADMIN",
                name="user_role",
            ),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=40), nullable=True),
        sa.Column("to_state", sa.String(length=40), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_events_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(
        op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False
    )
    op.create_index(
        "ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_entity_id"), "audit_events", ["entity_id"], unique=False
    )

    op.create_table(
        "notam_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_number", sa.String(length=32), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "PORTAL", "EMAIL", "AFTN", "UPLOAD", "HAND_DELIVERY", "RAW_TEXT",
                name="request_source",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "RECEIVED", "TRIAGE", "DRAFT", "REVIEW", "CHANGES_REQUESTED", "APPROVED",
                "PUBLISHING", "PUBLISHED", "REJECTED", "CANCELLED", name="workflow_status",
            ),
            nullable=False,
        ),
        sa.Column("originator_name", sa.String(length=200), nullable=False),
        sa.Column("originator_email", sa.String(length=320), nullable=True),
        sa.Column("originator_reference", sa.String(length=120), nullable=True),
        sa.Column("location_indicator", sa.String(length=4), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("requested_series", sa.Enum("A", "B", name="notam_series"), nullable=True),
        sa.Column("safety_critical", sa.Boolean(), nullable=False),
        sa.Column("acknowledgement_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_data", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence", sa.Integer(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_to_id"], ["users.id"], name=op.f("fk_notam_requests_assigned_to_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_notam_requests_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notam_requests")),
    )
    op.create_index(
        op.f("ix_notam_requests_location_indicator"),
        "notam_requests",
        ["location_indicator"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notam_requests_request_number"),
        "notam_requests",
        ["request_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notam_requests_safety_critical"),
        "notam_requests",
        ["safety_critical"],
        unique=False,
    )
    op.create_index(op.f("ix_notam_requests_status"), "notam_requests", ["status"], unique=False)
    op.create_index(
        "ix_notam_requests_status_received",
        "notam_requests",
        ["status", "received_at"],
        unique=False,
    )

    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("source_document", sa.String(length=200), nullable=False),
        sa.Column("source_revision", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("verified_rule_count", sa.Integer(), nullable=False),
        sa.Column("total_rule_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name=op.f("fk_rule_versions_approved_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_versions")),
        sa.UniqueConstraint("version", name=op.f("uq_rule_versions_version")),
    )
    op.create_index(op.f("ix_rule_versions_active"), "rule_versions", ["active"], unique=False)

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["notam_requests.id"],
            name=op.f("fk_attachments_request_id_notam_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"], ["users.id"], name=op.f("fk_attachments_uploaded_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("object_key", name=op.f("uq_attachments_object_key")),
    )
    op.create_index(op.f("ix_attachments_sha256"), "attachments", ["sha256"], unique=False)

    op.create_table(
        "notams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("series", sa.Enum("A", "B", name="notam_series"), nullable=False),
        sa.Column("kind", sa.Enum("NEW", "REPLACE", "CANCEL", name="notam_kind"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("replaces_notam_id", sa.Uuid(), nullable=True),
        sa.Column("fir", sa.String(length=4), nullable=False),
        sa.Column("q_code", sa.String(length=5), nullable=False),
        sa.Column("traffic", sa.String(length=2), nullable=False),
        sa.Column("purpose", sa.String(length=3), nullable=False),
        sa.Column("scope", sa.String(length=2), nullable=False),
        sa.Column("lower_limit", sa.String(length=3), nullable=False),
        sa.Column("upper_limit", sa.String(length=3), nullable=False),
        sa.Column("coordinates_radius", sa.String(length=15), nullable=False),
        sa.Column("item_a", sa.String(length=8), nullable=False),
        sa.Column("item_b", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_c", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_c_qualifier", sa.String(length=4), nullable=True),
        sa.Column("item_d", sa.Text(), nullable=True),
        sa.Column("item_e", sa.Text(), nullable=False),
        sa.Column("item_f", sa.String(length=40), nullable=True),
        sa.Column("item_g", sa.String(length=40), nullable=True),
        sa.Column("formatted_message", sa.Text(), nullable=False),
        sa.Column("aixm_payload", sa.JSON(), nullable=True),
        sa.Column("validation_result", sa.JSON(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=40), nullable=False),
        sa.Column("prepared_by_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name=op.f("fk_notams_approved_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by_id"], ["users.id"], name=op.f("fk_notams_prepared_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["replaces_notam_id"], ["notams.id"], name=op.f("fk_notams_replaces_notam_id_notams")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["notam_requests.id"],
            name=op.f("fk_notams_request_id_notam_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notams")),
        sa.UniqueConstraint("request_id", name=op.f("uq_notams_request_id")),
    )
    op.create_index(op.f("ix_notams_published_at"), "notams", ["published_at"], unique=False)
    op.create_index(
        "uq_notams_series_number_year", "notams", ["series", "serial_number", "year"], unique=True
    )

    op.create_table(
        "publication_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notam_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["notam_id"],
            ["notams.id"],
            name=op.f("fk_publication_deliveries_notam_id_notams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_deliveries")),
    )


def downgrade() -> None:
    op.drop_table("publication_deliveries")
    op.drop_index("uq_notams_series_number_year", table_name="notams")
    op.drop_index(op.f("ix_notams_published_at"), table_name="notams")
    op.drop_table("notams")
    op.drop_index(op.f("ix_attachments_sha256"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_index(op.f("ix_rule_versions_active"), table_name="rule_versions")
    op.drop_table("rule_versions")
    op.drop_index("ix_notam_requests_status_received", table_name="notam_requests")
    op.drop_index(op.f("ix_notam_requests_status"), table_name="notam_requests")
    op.drop_index(op.f("ix_notam_requests_safety_critical"), table_name="notam_requests")
    op.drop_index(op.f("ix_notam_requests_request_number"), table_name="notam_requests")
    op.drop_index(op.f("ix_notam_requests_location_indicator"), table_name="notam_requests")
    op.drop_table("notam_requests")
    op.drop_index(op.f("ix_audit_events_entity_id"), table_name="audit_events")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
