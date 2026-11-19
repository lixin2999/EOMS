from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.core.scope import ScopeContext, apply_scope

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """数据访问基类：统一注入数据域，禁止业务层拼接原始 SQL。"""

    model: type[T]
    default_order: str = "id"

    def scoped(self, ctx: ScopeContext, **scope_kwargs: str | None) -> Select:
        return apply_scope(select(self.model), ctx, self.model, **scope_kwargs)

    def get(self, db: Session, obj_id: int, ctx: ScopeContext, **scope_kwargs: str | None) -> T | None:
        stmt = self.scoped(ctx, **scope_kwargs).where(self.model.id == obj_id)  # type: ignore[attr-defined]
        return db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        db: Session,
        ctx: ScopeContext,
        *,
        stmt: Select | None = None,
        order_by: str | None = None,
        **scope_kwargs: str | None,
    ) -> list[T]:
        base = stmt if stmt is not None else self.scoped(ctx, **scope_kwargs)
        order = getattr(self.model, order_by or self.default_order, None)
        if order is not None:
            base = base.order_by(order.desc() if (order_by or self.default_order).endswith("_desc") else order)
        return list(db.execute(base).scalars().all())

    def paginate(
        self,
        db: Session,
        ctx: ScopeContext,
        params: PageParams,
        *,
        stmt: Select | None = None,
        order_by: Any = None,
        **scope_kwargs: str | None,
    ) -> dict:
        base = stmt if stmt is not None else self.scoped(ctx, **scope_kwargs)
        if order_by is not None:
            base = base.order_by(order_by)
        count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
        total = int(db.execute(count_stmt).scalar_one())
        items = list(db.execute(base.limit(params.page_size).offset(params.offset)).scalars().all())
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}
