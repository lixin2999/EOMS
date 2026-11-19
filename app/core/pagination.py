from __future__ import annotations

from datetime import datetime

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError

MAX_PAGE_SIZE = 100


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数，最大 100"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paginate(db: Session, statement: Select, params: PageParams) -> dict:
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())
    items = list(db.execute(statement.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def ensure_page_range(start: str | None, end: str | None) -> None:
    if start and end and start > end:
        raise BusinessRuleError("开始时间不能晚于结束时间")


def like_escape(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def date_span(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime] | None:
    if start and end:
        return start, end
    return None
