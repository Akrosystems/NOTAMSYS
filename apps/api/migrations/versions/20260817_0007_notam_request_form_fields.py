"""Add GCAA-AIS-NTM-FR01 field-for-field parity to notam_requests, plus
aip_supplement_reference on notams.

Revision ID: 20260817_0007
Revises: 20260817_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0007"
down_revision: str | None = "20260817_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

location_type = sa.Enum("AD", "FIR", "AIRSPACE", name="location_type")
limit_type = sa.Enum("FL", "AGL", "AMSL", name="limit_type")
notam_kind = sa.Enum("NEW", "REPLACE", "CANCEL", name="notam_kind")


def upgrade() -> None:
    bind = op.get_bind()
    location_type.create(bind, checkfirst=True)
    limit_type.create(bind, checkfirst=True)

    op.alter_column(
        "notam_requests",
        "location_indicator",
        existing_type=sa.String(length=4),
        type_=sa.String(length=60),
        existing_nullable=False,
    )
    op.add_column(
        "notam_requests",
        sa.Column("location_type", location_type, nullable=False, server_default="AD"),
    )
    op.add_column(
        "notam_requests",
        sa.Column("requested_kind", notam_kind, nullable=False, server_default="NEW"),
    )
    op.add_column("notam_requests", sa.Column("referenced_notam_number", sa.String(length=40), nullable=True))
    op.add_column("notam_requests", sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notam_requests", sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "notam_requests",
        sa.Column("end_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notam_requests",
        sa.Column("end_permanent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notam_requests",
        sa.Column("end_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("notam_requests", sa.Column("periods_of_activity", sa.Text(), nullable=True))
    op.add_column(
        "notam_requests",
        sa.Column("lower_limit_sfc", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("notam_requests", sa.Column("lower_limit_value", sa.String(length=10), nullable=True))
    op.add_column("notam_requests", sa.Column("lower_limit_type", limit_type, nullable=True))
    op.add_column(
        "notam_requests",
        sa.Column("upper_limit_unl", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("notam_requests", sa.Column("upper_limit_value", sa.String(length=10), nullable=True))
    op.add_column("notam_requests", sa.Column("upper_limit_type", limit_type, nullable=True))
    op.add_column("notam_requests", sa.Column("originator_organisation", sa.String(length=200), nullable=True))
    op.add_column("notam_requests", sa.Column("originator_phone", sa.String(length=40), nullable=True))

    op.add_column("notams", sa.Column("aip_supplement_reference", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("notams", "aip_supplement_reference")

    op.drop_column("notam_requests", "originator_phone")
    op.drop_column("notam_requests", "originator_organisation")
    op.drop_column("notam_requests", "upper_limit_type")
    op.drop_column("notam_requests", "upper_limit_value")
    op.drop_column("notam_requests", "upper_limit_unl")
    op.drop_column("notam_requests", "lower_limit_type")
    op.drop_column("notam_requests", "lower_limit_value")
    op.drop_column("notam_requests", "lower_limit_sfc")
    op.drop_column("notam_requests", "periods_of_activity")
    op.drop_column("notam_requests", "end_estimated")
    op.drop_column("notam_requests", "end_permanent")
    op.drop_column("notam_requests", "end_confirmed")
    op.drop_column("notam_requests", "end_at")
    op.drop_column("notam_requests", "start_at")
    op.drop_column("notam_requests", "referenced_notam_number")
    op.drop_column("notam_requests", "requested_kind")
    op.drop_column("notam_requests", "location_type")
    op.alter_column(
        "notam_requests",
        "location_indicator",
        existing_type=sa.String(length=60),
        type_=sa.String(length=4),
        existing_nullable=False,
    )

    bind = op.get_bind()
    location_type.drop(bind, checkfirst=True)
    limit_type.drop(bind, checkfirst=True)
