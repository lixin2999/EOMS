from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.finance import CostRecord
from app.models.iam import User
from app.services.cost.ledger import reverse_cost
from app.services.project.project import get_project

ZERO = Decimal("0.00")


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(CostRecord)
    condition = scope_condition(ctx, CostRecord, creator_attr="applicant_id")
    return stmt.where(condition) if condition is not None else stmt


def list_costs(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    project_id: int | None = None,
    biz_type: str | None = None,
    period: str | None = None,
    account_code: str | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if project_id:
        stmt = stmt.where(CostRecord.project_id == project_id)
    if biz_type:
        stmt = stmt.where(CostRecord.biz_type == biz_type)
    if period:
        stmt = stmt.where(CostRecord.period == period)
    if account_code:
        stmt = stmt.where(CostRecord.account_code == account_code)
    if keyword:
        stmt = stmt.where(
            or_(
                CostRecord.source_no.like(f"%{keyword}%"),
                CostRecord.biz_id == int(keyword) if keyword.isdigit() else false(),
            )
        )
    if date_from:
        stmt = stmt.where(CostRecord.occur_date >= date_from)
    if date_to:
        stmt = stmt.where(CostRecord.occur_date <= date_to)
    stmt = stmt.order_by(CostRecord.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    totals = db.execute(
        select(CostRecord.biz_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(CostRecord.id.in_([item.id for item in items]))
        .group_by(CostRecord.biz_type)
    ).all()
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "totals": {row[0]: Decimal(str(row[1])) for row in totals},
    }


def get_cost(db: Session, ctx: ScopeContext, cost_id: int) -> CostRecord:
    item = db.execute(_base_query(ctx).where(CostRecord.id == cost_id)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("成本记录不存在或无权访问")
    return item


def reverse(db: Session, user: User, ctx: ScopeContext, cost_id: int, reason: str) -> CostRecord:
    record = get_cost(db, ctx, cost_id)
    return reverse_cost(db, record.id, user, reason)


def project_cost_summary(db: Session, ctx: ScopeContext, project_id: int) -> dict:
    project = get_project(db, ctx, project_id)
    rows = db.execute(
        select(CostRecord.biz_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(CostRecord.project_id == project.id, CostRecord.status == "ACTIVE")
        .group_by(CostRecord.biz_type)
    ).all()
    totals = {row[0]: Decimal(str(row[1])) for row in rows}
    revenue = totals.get("RECEIVABLE", ZERO)
    cost = totals.get("PAYMENT", ZERO)
    expense = totals.get("EXPENSE", ZERO)
    gross = revenue - cost - expense
    return {
        "project_id": project.id,
        "revenue": revenue,
        "cost": cost,
        "expense": expense,
        "gross_profit": gross,
        "gross_margin": round(float(gross / revenue), 4) if revenue else 0.0,
        "receipt": totals.get("RECEIPT", ZERO),
        "cash_net": totals.get("RECEIPT", ZERO)
        - Decimal(
            str(
                db.execute(
                    select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
                        CostRecord.project_id == project.id,
                        CostRecord.biz_type == "PAYMENT",
                        CostRecord.status == "ACTIVE",
                        CostRecord.cash_date.is_not(None),
                    )
                ).scalar_one()
            )
        )
        - Decimal(
            str(
                db.execute(
                    select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
                        CostRecord.project_id == project.id,
                        CostRecord.biz_type == "EXPENSE",
                        CostRecord.status == "ACTIVE",
                        CostRecord.cash_date.is_not(None),
                    )
                ).scalar_one()
            )
        ),
        "budget": Decimal(str(project.budget_amount or 0)),
        "budget_usage": round(
            float((cost + expense) / Decimal(str(project.budget_amount)))
            if Decimal(str(project.budget_amount))
            else 0.0,
            4,
        ),
    }


def project_actual_cost(db: Session, project_id: int) -> Decimal:
    value = db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.project_id == project_id,
            CostRecord.biz_type.in_(["PAYMENT", "EXPENSE"]),
            CostRecord.status == "ACTIVE",
        )
    ).scalar_one()
    return Decimal(str(value or 0))
