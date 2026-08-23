"""Add Phase G experiment matrix and durable run queue.

Revision ID: 20260823_0003
Revises: 20260822_0002
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0003"
down_revision: str | None = "20260822_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan_digest", sa.String(length=71), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'planned'"), nullable=False
        ),
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
        "experiment_cell",
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("cell_id", sa.String(length=100), nullable=False),
        sa.Column("lane", sa.String(length=1), nullable=False),
        sa.Column("configuration_identity", sa.String(length=71), nullable=False),
        sa.Column("configuration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("repeat_target", sa.Integer(), nullable=False),
        sa.CheckConstraint("lane IN ('M', 'H')", name="ck_experiment_cell_lane"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("experiment_id", "cell_id"),
    )
    op.create_table(
        "experiment_pair",
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("pair_id", sa.String(length=100), nullable=False),
        sa.Column("left_cell_id", sa.String(length=100), nullable=False),
        sa.Column("right_cell_id", sa.String(length=100), nullable=False),
        sa.Column("intent", sa.String(length=50), nullable=False),
        sa.Column("definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("experiment_id", "pair_id"),
    )
    op.create_table(
        "experiment_ablation",
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("ablation_id", sa.String(length=100), nullable=False),
        sa.Column("base_cell_id", sa.String(length=100), nullable=False),
        sa.Column("variant_cell_id", sa.String(length=100), nullable=False),
        sa.Column("changed_dimension", sa.String(length=100), nullable=False),
        sa.Column("definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("experiment_id", "ablation_id"),
    )
    op.create_table(
        "experiment_run",
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("cell_id", sa.String(length=100), nullable=False),
        sa.Column("slot_id", sa.String(length=71), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False),
        sa.Column("slot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lane", sa.String(length=1), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("task_version", sa.String(length=100), nullable=False),
        sa.Column("task_digest", sa.String(length=71), nullable=False),
        sa.Column("repeat_index", sa.Integer(), nullable=False),
        sa.Column("paired_slot_identity", sa.String(length=71), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("lease_owner", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancellation_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("artifact_manifest_path", sa.Text(), nullable=True),
        sa.Column("evidence_digest", sa.String(length=71), nullable=True),
        sa.Column("normalized_outcome", sa.String(length=30), nullable=True),
        sa.Column("source_outcome", sa.String(length=100), nullable=True),
        sa.Column("failure_detail", sa.String(length=500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_calls", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("explicit_cost", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt >= 0", name="ck_experiment_run_attempt"),
        sa.CheckConstraint("lane IN ('M', 'H')", name="ck_experiment_run_lane"),
        sa.CheckConstraint("repeat_index >= 0", name="ck_experiment_run_repeat_index"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "cell_id"],
            ["experiment_cell.experiment_id", "experiment_cell.cell_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("slot_id"),
        sa.UniqueConstraint(
            "experiment_id",
            "cell_id",
            "task_id",
            "task_version",
            "task_digest",
            "repeat_index",
            name="uq_experiment_logical_run_slot",
        ),
    )
    op.create_index(
        "ix_experiment_run_claim",
        "experiment_run",
        ["status", "lease_expires_at", "slot_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_run_claim", table_name="experiment_run")
    op.drop_table("experiment_run")
    op.drop_table("experiment_ablation")
    op.drop_table("experiment_pair")
    op.drop_table("experiment_cell")
    op.drop_table("experiment")
