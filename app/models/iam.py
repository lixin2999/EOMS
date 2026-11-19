from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enable_audit_guard
from app.models.enums import UserStatus
from app.utils.datetime import now


class Company(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_company"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    tax_no: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)


class Dept(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_dept"
    __table_args__ = (Index("ix_sys_dept_company_parent", "company_id", "parent_id"),)

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(255), default="/", nullable=False)
    leader_user_id: Mapped[int | None] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_sys_user_username"),
        Index("ix_sys_user_company_dept", "company_id", "dept_id"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dept_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    real_name: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[str | None] = mapped_column(String(64))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(128))
    role_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE.value, nullable=False)
    is_super: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_login: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Role(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_role"

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(16), default="SELF", nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))


class Permission(Base, IdMixin):
    __tablename__ = "sys_permission"

    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    path: Mapped[str | None] = mapped_column(String(255))
    component: Mapped[str | None] = mapped_column(String(255))
    icon: Mapped[str | None] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RolePermission(Base, IdMixin):
    __tablename__ = "sys_role_permission"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_sys_role_permission_role_permission"),)

    role_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class AuditLog(Base, IdMixin):
    __tablename__ = "sys_audit_log"
    __table_args__ = (
        Index("ix_sys_audit_log_target", "target_type", "target_id"),
        Index("ix_sys_audit_log_created", "created_at"),
    )

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    ua: Mapped[str | None] = mapped_column(String(255))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class SysFile(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_file"
    __table_args__ = (Index("ix_sys_file_biz", "biz_type", "biz_id"),)

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    biz_type: Mapped[str | None] = mapped_column(String(64))
    biz_id: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hash: Mapped[str | None] = mapped_column(String(128), index=True)
    mime: Mapped[str | None] = mapped_column(String(128))
    uploader_id: Mapped[int | None] = mapped_column(Integer, index=True)


class SysDict(Base, IdMixin, TimestampMixin):
    __tablename__ = "sys_dict"
    __table_args__ = (UniqueConstraint("dict_type", "value", "company_id", name="uq_sys_dict_type_value_company"),)

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    dict_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))


class SysConfig(Base, IdMixin):
    __tablename__ = "sys_config"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(255))
    updated_by: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class LoginLog(Base, IdMixin):
    __tablename__ = "sys_login_log"
    __table_args__ = (Index("ix_sys_login_log_user_created", "user_id", "created_at"),)

    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    ua: Mapped[str | None] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


enable_audit_guard(AuditLog)
