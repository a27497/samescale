"""Add authoritative Phase-M attempt, resource, control, and budget ledgers.

Revision ID: 20260904_0006
Revises: 20260828_0005
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0006"
down_revision: str | None = "20260828_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "experiment_run_attempt",
        sa.Column("attempt_id", sa.String(71), nullable=False),
        sa.Column("run_id", sa.String(100), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("authorization_json", jsonb, nullable=True),
        sa.Column("reservation_digest", sa.String(71), nullable=True),
        sa.Column("current_state", sa.String(30), nullable=False),
        sa.Column("artifact_manifest_path", sa.Text(), nullable=True),
        sa.Column("evidence_digest", sa.String(71), nullable=True),
        sa.Column("terminal_reason", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_number >= 1", name="ck_run_attempt_number"),
        sa.CheckConstraint("role IN ('PRIMARY', 'RECOVERY')", name="ck_run_attempt_role"),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_run.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("run_id", "attempt_number", name="uq_run_attempt_number"),
    )
    op.create_index(
        "ix_run_attempt_current", "experiment_run_attempt", ["run_id", "attempt_number"]
    )
    op.create_table(
        "experiment_attempt_event",
        sa.Column("event_id", sa.String(71), nullable=False),
        sa.Column("attempt_id", sa.String(71), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(30), nullable=False),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("previous_event_digest", sa.String(71), nullable=True),
        sa.Column("event_digest", sa.String(71), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["experiment_run_attempt.attempt_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("attempt_id", "sequence", name="uq_attempt_event_sequence"),
        sa.UniqueConstraint("event_digest"),
    )
    op.create_index(
        "ix_attempt_event_chain", "experiment_attempt_event", ["attempt_id", "sequence"]
    )
    op.create_table(
        "experiment_resource_event",
        sa.Column("event_id", sa.String(71), nullable=False),
        sa.Column("attempt_id", sa.String(71), nullable=False),
        sa.Column("reservation_digest", sa.String(71), nullable=False),
        sa.Column("resource_envelope_identity", sa.String(71), nullable=False),
        sa.Column("usage_json", jsonb, nullable=False),
        sa.Column("evidence_reference_json", jsonb, nullable=True),
        sa.Column("event_digest", sa.String(71), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["experiment_run_attempt.attempt_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("event_digest"),
    )
    op.create_table(
        "experiment_control_event",
        sa.Column("event_id", sa.String(71), nullable=False),
        sa.Column("experiment_id", sa.String(100), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("control_type", sa.String(40), nullable=False),
        sa.Column("actor_identity", sa.String(71), nullable=False),
        sa.Column("authorization_identity", sa.String(71), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("selected_slot_ids_json", jsonb, nullable=False),
        sa.Column("preflight_digest", sa.String(71), nullable=True),
        sa.Column("budget_estimate_digest", sa.String(71), nullable=True),
        sa.Column("previous_event_digest", sa.String(71), nullable=True),
        sa.Column("event_digest", sa.String(71), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("event_digest"),
        sa.UniqueConstraint("experiment_id", "sequence", name="uq_control_event_sequence"),
    )
    op.create_index(
        "ix_control_event_chain", "experiment_control_event", ["experiment_id", "sequence"]
    )
    op.create_table(
        "budget_scope_ledger",
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("preflight_digest", sa.String(71), nullable=False),
        sa.Column("budget_estimate_digest", sa.String(71), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("ceilings_json", jsonb, nullable=False),
        sa.Column("reserved_totals_json", jsonb, nullable=False),
        sa.Column("consumed_totals_json", jsonb, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope_id"),
    )
    op.create_table(
        "budget_reservation",
        sa.Column("reservation_digest", sa.String(71), nullable=False),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("logical_unit_id", sa.String(71), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("receipt_json", jsonb, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scope_id"], ["budget_scope_ledger.scope_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("reservation_digest"),
        sa.UniqueConstraint("request_digest"),
    )
    op.create_index(
        "ix_budget_reservation_unit",
        "budget_reservation",
        ["scope_id", "logical_unit_id"],
    )
    op.create_foreign_key(
        "fk_run_attempt_reservation",
        "experiment_run_attempt",
        "budget_reservation",
        ["reservation_digest"],
        ["reservation_digest"],
    )
    op.create_foreign_key(
        "fk_resource_event_reservation",
        "experiment_resource_event",
        "budget_reservation",
        ["reservation_digest"],
        ["reservation_digest"],
    )
    op.create_table(
        "experiment_attempt_reconciliation",
        sa.Column("reconciliation_digest", sa.String(71), nullable=False),
        sa.Column("attempt_id", sa.String(71), nullable=False),
        sa.Column("resource_event_digest", sa.String(71), nullable=False),
        sa.Column("reservation_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("released_json", jsonb, nullable=False),
        sa.Column("receipt_json", jsonb, nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["experiment_run_attempt.attempt_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["resource_event_digest"], ["experiment_resource_event.event_id"]),
        sa.ForeignKeyConstraint(["reservation_digest"], ["budget_reservation.reservation_digest"]),
        sa.PrimaryKeyConstraint("reconciliation_digest"),
        sa.UniqueConstraint("attempt_id"),
    )


def downgrade() -> None:
    op.drop_table("experiment_attempt_reconciliation")
    op.drop_constraint(
        "fk_resource_event_reservation", "experiment_resource_event", type_="foreignkey"
    )
    op.drop_constraint("fk_run_attempt_reservation", "experiment_run_attempt", type_="foreignkey")
    op.drop_index("ix_budget_reservation_unit", table_name="budget_reservation")
    op.drop_table("budget_reservation")
    op.drop_table("budget_scope_ledger")
    op.drop_index("ix_control_event_chain", table_name="experiment_control_event")
    op.drop_table("experiment_control_event")
    op.drop_table("experiment_resource_event")
    op.drop_index("ix_attempt_event_chain", table_name="experiment_attempt_event")
    op.drop_table("experiment_attempt_event")
    op.drop_index("ix_run_attempt_current", table_name="experiment_run_attempt")
    op.drop_table("experiment_run_attempt")
