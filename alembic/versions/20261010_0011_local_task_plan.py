"""Immutable private single-Codex plans; no execution or historical-table changes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_0011"
down_revision: str | None = "20260915_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_plan_preflight",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("digest", sa.String(71), unique=True, nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "local_task_plan",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "preflight_id",
            sa.String(100),
            sa.ForeignKey("local_plan_preflight.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(36), unique=True, nullable=False),
        sa.Column("digest", sa.String(71), unique=True, nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.execute("""
        CREATE FUNCTION local_plan_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'local planning documents are immutable'; END; $$
    """)
    for name in ("local_plan_preflight", "local_task_plan"):
        op.execute(
            f"CREATE TRIGGER immutable_document BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION local_plan_immutable()"
        )


def downgrade() -> None:
    op.drop_table("local_task_plan")
    op.drop_table("local_plan_preflight")
    op.execute("DROP FUNCTION local_plan_immutable()")
