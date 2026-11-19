from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.utils.datetime import now


class Sequence(Base):
    __tablename__ = "sys_sequence"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class Notification(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_notification"
    __table_args__ = (Index("ix_sys_notification_user_read", "user_id", "read_at"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="SYSTEM", nullable=False)
    biz_type: Mapped[str | None] = mapped_column(String(64))
    biz_id: Mapped[int | None] = mapped_column(Integer)
    link: Mapped[str | None] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class IdempotencyKey(Base, IdMixin):
    __tablename__ = "sys_idempotency"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", "key", name="uq_sys_idempotency_company_user_key"),
        Index("ix_sys_idempotency_created", "created_at"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Outbox(Base, IdMixin):
    __tablename__ = "sys_outbox"
    __table_args__ = (Index("ix_sys_outbox_status_next", "status", "next_retry_at"),)

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class Customer(Base, IdMixin, TimestampMixin):
    """客户主档（报表"客户"维度所需，文档报表章节引用）。"""

    __tablename__ = "sys_customer"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_sys_customer_company_name"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    contact: Mapped[str | None] = mapped_column(String(64))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    creator_id: Mapped[int | None] = mapped_column(Integer)
