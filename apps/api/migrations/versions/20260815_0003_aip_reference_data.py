"""Add AIP reference-data tables.

Revision ID: 20260815_0003
Revises: 20260815_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0003"
down_revision: str | None = "20260815_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aip_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aip_datasets")),
        sa.UniqueConstraint("version", name=op.f("uq_aip_datasets_version")),
    )
    op.create_index(op.f("ix_aip_datasets_active"), "aip_datasets", ["active"], unique=False)

    op.create_table(
        "firs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("icao_code", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provenance", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["aip_datasets.id"],
            name=op.f("fk_firs_dataset_id_aip_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_firs")),
    )
    op.create_index(op.f("ix_firs_dataset_id"), "firs", ["dataset_id"], unique=False)
    op.create_index("uq_firs_dataset_icao", "firs", ["dataset_id", "icao_code"], unique=True)

    op.create_table(
        "aerodromes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("icao_code", sa.String(length=4), nullable=False),
        sa.Column("iata_code", sa.String(length=3), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("fir_id", sa.Uuid(), nullable=True),
        sa.Column("arp_latitude", sa.Float(), nullable=True),
        sa.Column("arp_longitude", sa.Float(), nullable=True),
        sa.Column("elevation_ft", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["aip_datasets.id"],
            name=op.f("fk_aerodromes_dataset_id_aip_datasets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fir_id"], ["firs.id"], name=op.f("fk_aerodromes_fir_id_firs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aerodromes")),
    )
    op.create_index(
        op.f("ix_aerodromes_dataset_id"), "aerodromes", ["dataset_id"], unique=False
    )
    op.create_index(
        op.f("ix_aerodromes_icao_code"), "aerodromes", ["icao_code"], unique=False
    )
    op.create_index(
        "uq_aerodromes_dataset_icao", "aerodromes", ["dataset_id", "icao_code"], unique=True
    )

    op.create_table(
        "airspace_refs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("designator", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("fir_id", sa.Uuid(), nullable=True),
        sa.Column("provenance", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["aip_datasets.id"],
            name=op.f("fk_airspace_refs_dataset_id_aip_datasets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fir_id"], ["firs.id"], name=op.f("fk_airspace_refs_fir_id_firs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_airspace_refs")),
    )
    op.create_index(
        op.f("ix_airspace_refs_dataset_id"), "airspace_refs", ["dataset_id"], unique=False
    )

    op.create_table(
        "runways",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aerodrome_id", sa.Uuid(), nullable=False),
        sa.Column("designator", sa.String(length=10), nullable=False),
        sa.Column("length_ft", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["aerodrome_id"],
            ["aerodromes.id"],
            name=op.f("fk_runways_aerodrome_id_aerodromes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runways")),
    )
    op.create_index(op.f("ix_runways_aerodrome_id"), "runways", ["aerodrome_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runways_aerodrome_id"), table_name="runways")
    op.drop_table("runways")
    op.drop_index(op.f("ix_airspace_refs_dataset_id"), table_name="airspace_refs")
    op.drop_table("airspace_refs")
    op.drop_index("uq_aerodromes_dataset_icao", table_name="aerodromes")
    op.drop_index(op.f("ix_aerodromes_icao_code"), table_name="aerodromes")
    op.drop_index(op.f("ix_aerodromes_dataset_id"), table_name="aerodromes")
    op.drop_table("aerodromes")
    op.drop_index("uq_firs_dataset_icao", table_name="firs")
    op.drop_index(op.f("ix_firs_dataset_id"), table_name="firs")
    op.drop_table("firs")
    op.drop_index(op.f("ix_aip_datasets_active"), table_name="aip_datasets")
    op.drop_table("aip_datasets")
