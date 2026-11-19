from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DomainMixin, IdMixin, TimestampMixin, VersionMixin
from app.models.enums import WorkflowStatus
from app.utils.datetime import now


class WorkflowDefinition(Base, IdMixin, TimestampMixin):
    __tablename__ = "wf_definition"
    __table_args__ = (UniqueConstraint("company_id", "code", "version", name="uq_wf_definition_company_code_version"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    nodes_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))


class WorkflowInstance(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "wf_instance"
    __table_args__ = (
        Index("ix_wf_instance_biz", "biz_type", "biz_id"),
        Index("ix_wf_instance_initiator_status", "initiator_id", "status"),
    )

    def_id: Mapped[int] = mapped_column(Integer, nullable=False)
    def_code: Mapped[str] = mapped_column(String(64), nullable=False)
    biz_type: Mapped[str] = mapped_column(String(64), nullable=False)
    biz_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    initiator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    current_node: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=WorkflowStatus.RUNNING.value, nullable=False, index=True)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    finish_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkflowTask(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "wf_task"
    __table_args__ = (
        Index("ix_wf_task_assignee_status", "assignee_id", "status"),
        Index("ix_wf_task_instance_node", "instance_id", "node_code"),
    )

    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    node_code: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    candidate_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    action: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(String(1000))
    mode: Mapped[str] = mapped_column(String(16), default="ANY", nullable=False)
    seq: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    arrive_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    finish_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkflowRecord(Base, IdMixin):
    __tablename__ = "wf_record"
    __table_args__ = (Index("ix_wf_record_instance_created", "instance_id", "created_at"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    node_code: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(128))
    operator_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000))
    attachments: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class WorkflowCc(Base, IdMixin):
    __tablename__ = "wf_cc"
    __table_args__ = (Index("ix_wf_cc_instance_user", "instance_id", "user_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
