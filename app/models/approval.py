from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DomainMixin, IdMixin, TimestampMixin, VersionMixin
from app.models.enums import DocumentStatus, ExpenseStatus, LeaveStatus


class Expense(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "biz_expense"
    __table_args__ = (
        UniqueConstraint("no", name="uq_biz_expense_no"),
        Index("ix_biz_expense_applicant_status", "applicant_id", "status"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), default="OTHER", nullable=False)
    amount_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    items_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    invoices_file_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    payee: Mapped[str | None] = mapped_column(String(128))
    remark: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default=ExpenseStatus.DRAFT.value, nullable=False, index=True)
    instance_id: Mapped[int | None] = mapped_column(Integer, index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class ExpenseItem(Base, IdMixin):
    __tablename__ = "biz_expense_item"
    __table_args__ = (Index("ix_biz_expense_item_expense", "expense_id"),)

    expense_id: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    occur_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(500))
    file_id: Mapped[int | None] = mapped_column(Integer)


class Leave(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "biz_leave"
    __table_args__ = (
        UniqueConstraint("no", name="uq_biz_leave_no"),
        Index("ix_biz_leave_applicant_status", "applicant_id", "status"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), default="ANNUAL", nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    handover_user_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=LeaveStatus.DRAFT.value, nullable=False, index=True)
    instance_id: Mapped[int | None] = mapped_column(Integer, index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class LeaveBalance(Base, IdMixin, TimestampMixin):
    __tablename__ = "biz_leave_balance"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", "year", "type", name="uq_biz_leave_balance_user_year_type"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0, nullable=False)
    used: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0, nullable=False)
    remain: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=0, nullable=False)


class Document(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "biz_document"
    __table_args__ = (
        UniqueConstraint("doc_no", name="uq_biz_document_doc_no"),
        Index("ix_biz_document_creator_status", "creator_id", "status"),
    )

    doc_no: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="INSTITUTION", nullable=False)
    secret_level: Mapped[str] = mapped_column(String(16), default="INTERNAL", nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[int | None] = mapped_column(Integer)
    effect_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.DRAFT.value, nullable=False, index=True)
    instance_id: Mapped[int | None] = mapped_column(Integer, index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
