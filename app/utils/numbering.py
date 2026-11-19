from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.platform import Sequence


def _next_sequence(db: Session, name: str) -> int:
    row = db.execute(select(Sequence).where(Sequence.name == name).with_for_update()).scalar_one_or_none()
    if row is None:
        try:
            with db.begin_nested():
                row = Sequence(name=name, current=1)
                db.add(row)
            db.flush()
            return 1
        except IntegrityError:
            row = db.execute(select(Sequence).where(Sequence.name == name).with_for_update()).scalar_one()
    row.current = int(row.current) + 1
    db.flush()
    return int(row.current)


def next_no(
    db: Session,
    prefix: str,
    *,
    company_code: str | None = None,
    period: str | None = None,
    width: int = 4,
) -> str:
    """生成全局唯一业务编号：前缀-年月-公司码-流水；同一事务内行锁保证不重号。"""
    parts = [prefix.upper()]
    if period:
        parts.append(period.replace("-", ""))
    if company_code:
        parts.append(company_code.upper())
    sequence_name = ":".join(parts)
    current = _next_sequence(db, sequence_name)
    parts.append(str(current).zfill(width))
    return "-".join(parts)


def project_no(db: Session, company_code: str, year: int) -> str:
    return next_no(db, "PRJ", company_code=company_code, period=str(year), width=4)
