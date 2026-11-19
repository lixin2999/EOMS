from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DomainMixin, IdMixin, TimestampMixin, VersionMixin
from app.models.enums import ContractStatus, VendorStatus


class Vendor(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "vd_vendor"
    __table_args__ = (
        UniqueConstraint("code", name="uq_vd_vendor_code"),
        Index("ix_vd_vendor_status_level", "status", "level"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_no: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(32), default="SERVICE", nullable=False)
    level: Mapped[str] = mapped_column(String(8), default="C", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=VendorStatus.PENDING.value, nullable=False, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    intro: Mapped[str | None] = mapped_column(String(2000))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    blacklist_reason: Mapped[str | None] = mapped_column(String(500))
    instance_id: Mapped[int | None] = mapped_column(Integer)


class VendorContact(Base, IdMixin, TimestampMixin):
    __tablename__ = "vd_vendor_contact"
    __table_args__ = (Index("ix_vd_vendor_contact_vendor", "vendor_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(64))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(128))
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)


class VendorBank(Base, IdMixin, TimestampMixin):
    __tablename__ = "vd_vendor_bank"
    __table_args__ = (Index("ix_vd_vendor_bank_vendor", "vendor_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bank_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_no_enc: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)


class VendorLicense(Base, IdMixin, TimestampMixin):
    __tablename__ = "vd_vendor_license"
    __table_args__ = (Index("ix_vd_vendor_license_vendor", "vendor_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    no: Mapped[str | None] = mapped_column(String(128))
    file_id: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class Contract(Base, IdMixin, DomainMixin, TimestampMixin, VersionMixin):
    __tablename__ = "vd_contract"
    __table_args__ = (
        UniqueConstraint("no", name="uq_vd_contract_no"),
        Index("ix_vd_contract_vendor_status", "vendor_id", "status"),
        Index("ix_vd_contract_project", "project_id"),
    )

    no: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    sign_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    pay_terms_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    file_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=ContractStatus.DRAFT.value, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(1000))


class VendorProject(Base, IdMixin, TimestampMixin):
    __tablename__ = "vd_vendor_project"
    __table_args__ = (
        UniqueConstraint("vendor_id", "project_id", "contract_id", name="uq_vd_vendor_project_vendor_project_contract"),
        Index("ix_vd_vendor_project_project", "project_id"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(64), default="分包商", nullable=False)
    contract_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    settled_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)


class Evaluation(Base, IdMixin, TimestampMixin):
    __tablename__ = "vd_evaluation"
    __table_args__ = (Index("ix_vd_evaluation_vendor_date", "vendor_id", "eval_date"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer)
    evaluator_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    schedule_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    cooperate_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    grade: Mapped[str] = mapped_column(String(8), default="C", nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000))
    eval_date: Mapped[date] = mapped_column(Date, nullable=False)
