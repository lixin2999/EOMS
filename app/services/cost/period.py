from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.models.enums import PeriodStatus
from app.models.finance import CostRecord, Period
from app.models.iam import User
from app.services.iam.audit import write_audit
from app.utils.datetime import now, parse_period

OPEN = PeriodStatus.OPEN.value
CLOSED = PeriodStatus.CLOSED.value


def list_periods(db: Session, company_id: int, year: int | None = None) -> list[Period]:
    stmt = select(Period).where(Period.company_id == company_id)
    if year:
        stmt = stmt.where(Period.period.like(f"{year}-%"))
    return list(db.execute(stmt.order_by(Period.period.desc())).scalars().all())


def get_period(db: Session, company_id: int, period: str) -> Period:
    parse_period(period)
    row = db.execute(
        select(Period).where(Period.company_id == company_id, Period.period == period)
    ).scalar_one_or_none()
    if row is None:
        row = Period(company_id=company_id, period=period, status=OPEN)
        db.add(row)
        db.flush()
    return row


def close_period(db: Session, user: User, period: str, remark: str | None = None) -> Period:
    row = get_period(db, user.company_id, period)
    if row.status == CLOSED:
        raise BusinessRuleError(f"期间 {period} 已关账")
    row.status = CLOSED
    row.closed_by = user.id
    row.closed_at = now()
    row.remark = (remark or "")[:255]
    db.flush()
    project_ids = db.execute(
        select(CostRecord.project_id)
        .where(
            CostRecord.company_id == user.company_id,
            CostRecord.period == period,
            CostRecord.project_id.is_not(None),
        )
        .distinct()
    ).scalars()
    from app.models.project import Project
    from app.services.report.pnl import generate_project_pnl

    for project_id in project_ids:
        project = db.get(Project, project_id)
        if project is not None:
            generate_project_pnl(db, project, period=period, persist=True)
    write_audit(db, user=user, action="CLOSE_PERIOD", target_type="PERIOD", target_id=row.id, after={"period": period})
    return row


def reopen_period(db: Session, user: User, period: str, reason: str) -> Period:
    if not reason or len(reason.strip()) < 3:
        raise BusinessRuleError("请填写反关账原因")
    row = get_period(db, user.company_id, period)
    if row.status != CLOSED:
        raise BusinessRuleError(f"期间 {period} 未关账")
    row.status = OPEN
    row.closed_by = None
    row.closed_at = None
    row.remark = f"反关账：{reason}"[:255]
    db.flush()
    write_audit(
        db,
        user=user,
        action="REOPEN_PERIOD",
        target_type="PERIOD",
        target_id=row.id,
        after={"period": period, "reason": reason},
    )
    # 反关账后立即补记该期间的待归集成本，避免财务再手工补录。
    from app.services.cost.pending import post_pending_costs

    post_pending_costs(db, company_id=user.company_id, limit=500)
    return row
