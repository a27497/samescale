from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class ExperimentRecord(Base):
    __tablename__ = "experiment"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'planned'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentCellRecord(Base):
    __tablename__ = "experiment_cell"

    experiment_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("experiment.id", ondelete="CASCADE"), primary_key=True
    )
    cell_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    lane: Mapped[str] = mapped_column(String(1), nullable=False)
    configuration_identity: Mapped[str] = mapped_column(String(71), nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    repeat_target: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (CheckConstraint("lane IN ('M', 'H')", name="ck_experiment_cell_lane"),)


class ExperimentRunRecord(Base):
    __tablename__ = "experiment_run"

    run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    slot_id: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    slot_order: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    lane: Mapped[str] = mapped_column(String(1), nullable=False)
    task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_version: Mapped[str] = mapped_column(String(100), nullable=False)
    task_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    paired_slot_identity: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'queued'"))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    artifact_manifest_path: Mapped[str | None] = mapped_column(Text)
    evidence_digest: Mapped[str | None] = mapped_column(String(71))
    normalized_outcome: Mapped[str | None] = mapped_column(String(30))
    source_outcome: Mapped[str | None] = mapped_column(String(100))
    failure_detail: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    tool_calls: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    explicit_cost: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "cell_id"],
            ["experiment_cell.experiment_id", "experiment_cell.cell_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "experiment_id",
            "cell_id",
            "task_id",
            "task_version",
            "task_digest",
            "repeat_index",
            name="uq_experiment_logical_run_slot",
        ),
        CheckConstraint("lane IN ('M', 'H')", name="ck_experiment_run_lane"),
        CheckConstraint("repeat_index >= 0", name="ck_experiment_run_repeat_index"),
        CheckConstraint("attempt >= 0", name="ck_experiment_run_attempt"),
        Index("ix_experiment_run_claim", "status", "lease_expires_at", "slot_order"),
    )


class ExperimentPairRecord(Base):
    __tablename__ = "experiment_pair"

    experiment_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("experiment.id", ondelete="CASCADE"), primary_key=True
    )
    pair_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    left_cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    right_cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class ExperimentAblationRecord(Base):
    __tablename__ = "experiment_ablation"

    experiment_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("experiment.id", ondelete="CASCADE"), primary_key=True
    )
    ablation_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    base_cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    variant_cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    changed_dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
