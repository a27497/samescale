"""Add the immutable Unified Registry Lite snapshot ledger.

Revision ID: 20260828_0005
Revises: 20260823_0004
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0005"
down_revision: str | None = "20260823_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registry_experiment_snapshot",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("snapshot_digest", sa.String(length=71), nullable=False),
        sa.Column("methodology_id", sa.String(length=100), nullable=False),
        sa.Column("methodology_digest", sa.String(length=71), nullable=False),
        sa.Column("preflight_status", sa.String(length=30), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_digest"),
    )


def downgrade() -> None:
    op.drop_table("registry_experiment_snapshot")
