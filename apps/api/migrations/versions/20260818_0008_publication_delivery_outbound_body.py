"""Add publication_deliveries.outbound_body (AFTN bridge pull queue).

Revision ID: 20260818_0008
Revises: 20260817_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0008"
down_revision: str | None = "20260817_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publication_deliveries", sa.Column("outbound_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("publication_deliveries", "outbound_body")
