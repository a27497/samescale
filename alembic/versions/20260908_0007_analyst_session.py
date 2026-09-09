"""Persist bounded Analyst investigations, usage and review-only approvals.

Revision ID: 20260908_0007
Revises: 20260904_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0007"
down_revision: str | None = "20260904_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyst_session",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(100),
            sa.ForeignKey("experiment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_analyst_session_experiment_id", "analyst_session", ["experiment_id"])


def downgrade() -> None:
    op.drop_table("analyst_session")
