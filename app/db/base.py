from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, MetaData, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.datetime import now

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class DomainMixin:
    """数据域：公司（租户）+ 部门 + 项目 + 创建人，支撑行级隔离。"""

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dept_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AuditImmutableMixin:
    """审计/留痕表只增不改：ORM 层拦截更新与删除。"""

    __abstract__ = True


def _prevent_mutation(mapper, connection, target) -> None:  # noqa: ARG001, ANN001
    raise ValueError("审计日志只允许追加，不允许修改或删除")


def enable_audit_guard(model: type) -> None:
    event.listen(model, "before_update", _prevent_mutation)
    event.listen(model, "before_delete", _prevent_mutation)
