from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base
from harnesslab.db.models.experiment import JSON_DOCUMENT


class LocalExecutionAuthorizationRecord(Base):
    __tablename__ = "local_execution_authorization"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("local_task_plan.id"), unique=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    digest: Mapped[str] = mapped_column(String(71), unique=True, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class LocalExecutionAttemptRecord(Base):
    __tablename__ = "local_execution_attempt"
    run_id: Mapped[str] = mapped_column(ForeignKey("execution_lease.run_id"), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("local_execution_authorization.id"), unique=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("local_task_plan.id"), unique=True, nullable=False
    )


class LocalExecutionResultRecord(Base):
    __tablename__ = "local_execution_result"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("local_execution_attempt.run_id"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(71), unique=True, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
