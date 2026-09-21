"""Append-only local Harness preset selections."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0010"
down_revision: str | None = "20260915_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_harness_configuration",
        sa.Column("configuration_id", sa.String(40), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("configuration_json", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_harness_configuration")
