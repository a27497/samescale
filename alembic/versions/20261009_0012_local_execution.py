"""Single-slot execution authorization, attempts and immutable results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261009_0012"
down_revision: str | None = "20261010_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_execution_authorization",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(100),
            sa.ForeignKey("local_task_plan.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(36), unique=True, nullable=False),
        sa.Column("digest", sa.String(71), unique=True, nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "local_execution_attempt",
        sa.Column(
            "run_id", sa.String(100), sa.ForeignKey("execution_lease.run_id"), primary_key=True
        ),
        sa.Column(
            "authorization_id",
            sa.String(100),
            sa.ForeignKey("local_execution_authorization.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.String(100),
            sa.ForeignKey("local_task_plan.id"),
            unique=True,
            nullable=False,
        ),
    )
    op.create_table(
        "local_execution_result",
        sa.Column(
            "run_id",
            sa.String(100),
            sa.ForeignKey("local_execution_attempt.run_id"),
            primary_key=True,
        ),
        sa.Column("digest", sa.String(71), unique=True, nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    for name in (
        "local_execution_authorization",
        "local_execution_attempt",
        "local_execution_result",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_document BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION local_plan_immutable()"
        )


def downgrade() -> None:
    for name in (
        "local_execution_result",
        "local_execution_attempt",
        "local_execution_authorization",
    ):
        op.drop_table(name)
