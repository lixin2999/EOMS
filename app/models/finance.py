from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DomainMixin, IdMixin, TimestampMixin, VersionMixin
from app.models.enums import PeriodStatus
from app.utils.datetime import now


class Account(Base, IdMixin, TimestampMixin):
    __tablename__ = "fin_account"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_fin_account_company_code"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(16), default="EXPENSE", nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))


class Budget(Base, IdMixin, TimestampMixin, VersionMixin):
    __tablename__ = "fin_budget"
    __table_args__ = (
        UniqueConstraint("company_id", "project_id", "account_code", "year", name="uq_fin_budget_project_account_year"),
        Index("ix_fin_budget_project_year", "project_id", "year"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(String(32), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))
    creator_id: Mapped[int | None] = mapped_column(Integer)


class CostRecord(Base, IdMixin):
    __tablename__ = "fin_cost_record"
    __table_args__ = (
        UniqueConstraint("record_key", name="uq_fin_cost_record_record_key"),
        Index("ix_fin_cost_record_project_period", "project_id", "period"),
        Index("ix_fin_cost_record_biz", "biz_type", "biz_id"),
        Index("ix_fin_cost_record_account", "account_code"),
    )

    record_key: Mapped[str] = mapped_column(String(160), nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dept_id: Mapped[int | None] = mapped_column(Integer, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    biz_type: Mapped[str] = mapped_column(String(16), nullable=False)
    biz_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    occur_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer)
    contract_id: Mapped[int | None] = mapped_column(Integer)
    applicant_id: Mapped[int | None] = mapped_column(Integer)
    source_no: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    cash_date: Mapped[date | None] = mapped_column(Date)
    is_reversal: Mapped[bool] = mapped_column(default=False, nullable=False)
    reversal_of_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Payment(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "fin_payment"
    __table_args__ = (
        UniqueConstraint("no", name="uq_fin_payment_no"),
        Index("ix_fin_payment_status_date", "status", "pay_date"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor_id: Mapped[int | None] = mapped_column(Integer, index=True)
    contract_id: Mapped[int | None] = mapped_column(Integer, index=True)
    expense_id: Mapped[int | None] = mapped_column(Integer)
    applicant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    pay_date: Mapped[date | None] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(32), default="BANK", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    account_code: Mapped[str] = mapped_column(String(32), default="5401", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(1000))
    installments_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(Integer)


class Receipt(Base, IdMixin, DomainMixin, TimestampMixin):
    __tablename__ = "fin_receipt"
    __table_args__ = (
        UniqueConstraint("no", name="uq_fin_receipt_no"),
        Index("ix_fin_receipt_project_date", "project_id", "receipt_date"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer)
    contract_id: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(32), default="BANK", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="REGISTERED", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(1000))


class RevenueConfirm(Base, IdMixin, DomainMixin, TimestampMixin):
    __tablename__ = "fin_revenue_confirm"
    __table_args__ = (
        UniqueConstraint("no", name="uq_fin_revenue_confirm_no"),
        Index("ix_fin_revenue_confirm_project_period", "project_id", "period"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer)
    contract_id: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    confirm_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="MANUAL", nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(1000))


class Period(Base, IdMixin, TimestampMixin):
    __tablename__ = "fin_period"
    __table_args__ = (UniqueConstraint("company_id", "period", name="uq_fin_period_company_period"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PeriodStatus.OPEN.value, nullable=False)
    closed_by: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    remark: Mapped[str | None] = mapped_column(String(255))


class ProjectPnl(Base, IdMixin):
    __tablename__ = "fin_project_pnl"
    __table_args__ = (
        UniqueConstraint("project_id", "period", name="uq_fin_project_pnl_project_period"),
        Index("ix_fin_project_pnl_period", "period"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dept_id: Mapped[int | None] = mapped_column(Integer)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    gross_margin: Mapped[float] = mapped_column(default=0.0, nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    cost_variance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    milestone_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
