from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DomainMixin, IdMixin, TimestampMixin, VersionMixin
from app.models.enums import ProjectStage, ProjectStatus
from app.utils.datetime import now


class Project(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "pm_project"
    __table_args__ = (
        UniqueConstraint("no", name="uq_pm_project_no"),
        Index("ix_pm_project_stage_status", "stage", "status"),
        Index("ix_pm_project_manager", "manager_id"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="OTHER", nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True)
    manager_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), default=ProjectStage.LAUNCH.value, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default=ProjectStatus.PENDING.value, nullable=False, index=True)
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    contract_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    secret_level: Mapped[str] = mapped_column(String(16), default="INTERNAL", nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    close_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class ProjectMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "pm_project_member"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_pm_project_member_project_user"),
        Index("ix_pm_project_member_user", "user_id"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="MEMBER", nullable=False)
    join_at: Mapped[date | None] = mapped_column(Date)


class Initiation(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "pm_initiation"
    __table_args__ = (Index("ix_pm_initiation_project", "project_id"),)

    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    background: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    goal: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    estimate_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    estimate_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    risk_desc: Mapped[str | None] = mapped_column(String(2000))
    instance_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)


class WBS(Base, IdMixin, TimestampMixin):
    __tablename__ = "pm_wbs"
    __table_args__ = (Index("ix_pm_wbs_project_parent", "project_id", "parent_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_milestone: Mapped[bool] = mapped_column(default=False, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Task(Base, IdMixin, TimestampMixin, VersionMixin):
    __tablename__ = "pm_task"
    __table_args__ = (
        Index("ix_pm_task_project_status", "project_id", "status"),
        Index("ix_pm_task_owner", "owner_id"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    wbs_id: Mapped[int | None] = mapped_column(Integer, index=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="TODO", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    estimate_hours: Mapped[Decimal] = mapped_column(Numeric(10, 1), default=0, nullable=False)
    actual_hours: Mapped[Decimal] = mapped_column(Numeric(10, 1), default=0, nullable=False)


class TaskBaseline(Base, IdMixin):
    __tablename__ = "pm_task_baseline"
    __table_args__ = (Index("ix_pm_task_baseline_project_version", "project_id", "baseline_version"),)

    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[int | None] = mapped_column(Integer)
    wbs_code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    estimate_hours: Mapped[Decimal] = mapped_column(Numeric(10, 1), default=0, nullable=False)
    baseline_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Milestone(Base, IdMixin, TimestampMixin):
    __tablename__ = "pm_milestone"
    __table_args__ = (Index("ix_pm_milestone_project", "project_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_date: Mapped[date | None] = mapped_column(Date)
    actual_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    acceptance_file_id: Mapped[int | None] = mapped_column(Integer)


class Change(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "pm_change"
    __table_args__ = (Index("ix_pm_change_project_status", "project_id", "status"),)

    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    before_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    after_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    instance_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)


class Issue(Base, IdMixin, TimestampMixin):
    __tablename__ = "pm_issue"
    __table_args__ = (Index("ix_pm_issue_project_status", "project_id", "status"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    solution: Mapped[str | None] = mapped_column(String(2000))
    creator_id: Mapped[int | None] = mapped_column(Integer)


class Risk(Base, IdMixin, TimestampMixin):
    __tablename__ = "pm_risk"
    __table_args__ = (Index("ix_pm_risk_project_status", "project_id", "status"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    solution: Mapped[str | None] = mapped_column(String(2000))
    creator_id: Mapped[int | None] = mapped_column(Integer)


class Acceptance(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "pm_acceptance"
    __table_args__ = (Index("ix_pm_acceptance_project_status", "project_id", "status"),)

    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    acceptor: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(16), default="PASS", nullable=False)
    sign_file_id: Mapped[int | None] = mapped_column(Integer)
    accept_date: Mapped[date | None] = mapped_column(Date)
    accept_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(1000))
    instance_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)


class Archive(Base, IdMixin):
    __tablename__ = "pm_project_archive"
    __table_args__ = (Index("ix_pm_project_archive_project", "project_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    archived_by: Mapped[int | None] = mapped_column(Integer)


class ProjectReport(Base, IdMixin, TimestampMixin):
    """项目周报/月报。"""

    __tablename__ = "pm_report"
    __table_args__ = (Index("ix_pm_report_project_period", "project_id", "period"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="WEEKLY", nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    issues: Mapped[str | None] = mapped_column(Text)
    next_plan: Mapped[str | None] = mapped_column(Text)
    reporter_id: Mapped[int] = mapped_column(Integer, nullable=False)
