"""Local connection revisions and credential metadata; secret values stay outside PostgreSQL."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0009"
down_revision: str | None = "20260915_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_credential",
        sa.Column("credential_id", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("storage_reference", sa.String(32), nullable=False),
    )
    op.create_table(
        "local_connection",
        sa.Column("connection_id", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("endpoint_storage_reference", sa.String(32), nullable=False),
        sa.Column("configuration_json", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_connection")
    op.drop_table("local_credential")
