"""Add Phase H Judge calibration persistence.

Revision ID: 20260823_0004
Revises: 20260823_0003
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0004"
down_revision: str | None = "20260823_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_calibration",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("plan_digest", sa.String(length=71), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'planned'"), nullable=False
        ),
        sa.Column("report_json_path", sa.Text(), nullable=True),
        sa.Column("report_markdown_path", sa.Text(), nullable=True),
        sa.Column("report_digest", sa.String(length=71), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_digest"),
    )
    op.create_table(
        "judge_evaluation",
        sa.Column("evaluation_id", sa.String(length=80), nullable=False),
        sa.Column("calibration_id", sa.String(length=100), nullable=False),
        sa.Column("judge_cell_id", sa.String(length=100), nullable=False),
        sa.Column("case_id", sa.String(length=100), nullable=False),
        sa.Column("repeat_index", sa.Integer(), nullable=False),
        sa.Column("order_variant", sa.String(length=30), nullable=False),
        sa.Column("slot_id", sa.String(length=71), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False),
        sa.Column("slot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("artifact_manifest_path", sa.Text(), nullable=True),
        sa.Column("artifact_digest", sa.String(length=71), nullable=True),
        sa.Column("requested_judge_model", sa.String(length=200), nullable=False),
        sa.Column("observed_judge_model", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["calibration_id"], ["judge_calibration.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evaluation_id"),
        sa.UniqueConstraint("slot_id"),
        sa.UniqueConstraint(
            "calibration_id",
            "judge_cell_id",
            "case_id",
            "repeat_index",
            "order_variant",
            name="uq_judge_logical_evaluation_slot",
        ),
    )


def downgrade() -> None:
    op.drop_table("judge_evaluation")
    op.drop_table("judge_calibration")
