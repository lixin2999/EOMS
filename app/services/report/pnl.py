from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.finance import CostRecord, ProjectPnl
from app.models.project import Project
from app.services.project.execution import milestone_rate
from app.services.project.project import get_project
from app.utils.datetime import now
from app.utils.money import safe_ratio

ZERO = Decimal("0.00")


def compute_project_pnl(db: Session, project: Project, period: str | None = None) -> dict:
    stmt = select(CostRecord.biz_type, CostRecord.account_code, func.coalesce(func.sum(CostRecord.amount), 0)).where(
        CostRecord.project_id == project.id, CostRecord.status == "ACTIVE"
    )
    if period:
        stmt = stmt.where(CostRecord.period == period)
    rows = db.execute(stmt.group_by(CostRecord.biz_type, CostRecord.account_code)).all()
    revenue = ZERO
    cost = ZERO
    expense = ZERO
    revenue_by_account: dict[str, Decimal] = {}
    cost_by_account: dict[str, Decimal] = {}
    for biz_type, account_code, amount in rows:
        value = Decimal(str(amount or 0))
        if biz_type == "RECEIVABLE":
            revenue += value
            revenue_by_account[account_code] = revenue_by_account.get(account_code, ZERO) + value
        elif biz_type == "PAYMENT":
            cost += value
            cost_by_account[account_code] = cost_by_account.get(account_code, ZERO) + value
        elif biz_type == "EXPENSE":
            expense += value
            cost_by_account[account_code] = cost_by_account.get(account_code, ZERO) + value
    gross = revenue - cost - expense
    budget = Decimal(str(project.budget_amount or 0))
    return {
        "project_id": project.id,
        "project_no": project.no,
        "project_name": project.name,
        "dept_id": project.dept_id,
        "period": period or "TOTAL",
        "revenue": revenue,
        "cost": cost,
        "expense": expense,
        "gross_profit": gross,
        "gross_margin": safe_ratio(gross, revenue),
        "budget_amount": budget,
        "cost_variance": budget - (cost + expense),
        "budget_usage": safe_ratio(cost + expense, budget),
        "milestone_rate": milestone_rate(db, project.id),
        "revenue_by_account": {key: str(value) for key, value in revenue_by_account.items()},
        "cost_by_account": {key: str(value) for key, value in cost_by_account.items()},
    }


def generate_project_pnl(db: Session, project: Project, period: str | None = None, persist: bool = True) -> dict:
    period = period or now().strftime("%Y-%m")
    data = compute_project_pnl(db, project, period=None)
    if not persist:
        return data
    row = db.execute(
        select(ProjectPnl).where(ProjectPnl.project_id == project.id, ProjectPnl.period == period)
    ).scalar_one_or_none()
    if row is None:
        row = ProjectPnl(
            company_id=project.company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            period=period,
        )
        db.add(row)
    row.revenue = data["revenue"]
    row.cost = data["cost"]
    row.expense = data["expense"]
    row.gross_profit = data["gross_profit"]
    row.gross_margin = data["gross_margin"]
    row.budget_amount = data["budget_amount"]
    row.cost_variance = data["cost_variance"]
    row.milestone_rate = data["milestone_rate"]
    row.payload = {
        "revenue_by_account": data["revenue_by_account"],
        "cost_by_account": data["cost_by_account"],
        "budget_usage": data["budget_usage"],
        "scope": "TOTAL",
    }
    row.generated_at = now()
    db.flush()
    return {**data, "period": period, "snapshot_id": row.id, "generated_at": row.generated_at.isoformat()}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(ProjectPnl)
    condition = scope_condition(ctx, ProjectPnl, creator_attr=None)
    return stmt.where(condition) if condition is not None else stmt


def list_pnl(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    project_id: int | None = None,
    period: str | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if project_id:
        stmt = stmt.where(ProjectPnl.project_id == project_id)
    if period:
        stmt = stmt.where(ProjectPnl.period == period)
    stmt = stmt.order_by(ProjectPnl.period.desc(), ProjectPnl.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def project_pnl_detail(db: Session, ctx: ScopeContext, project_id: int) -> dict:
    project = get_project(db, ctx, project_id)
    total = compute_project_pnl(db, project, period=None)
    monthly_rows = db.execute(
        select(CostRecord.period, CostRecord.biz_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(CostRecord.project_id == project.id, CostRecord.status == "ACTIVE")
        .group_by(CostRecord.period, CostRecord.biz_type)
        .order_by(CostRecord.period)
    ).all()
    monthly: dict[str, dict[str, Decimal]] = {}
    for period, biz_type, amount in monthly_rows:
        monthly.setdefault(period, {"revenue": ZERO, "cost": ZERO, "expense": ZERO})
        if biz_type == "RECEIVABLE":
            monthly[period]["revenue"] += Decimal(str(amount))
        elif biz_type == "PAYMENT":
            monthly[period]["cost"] += Decimal(str(amount))
        elif biz_type == "EXPENSE":
            monthly[period]["expense"] += Decimal(str(amount))
    trend = []
    for period, values in sorted(monthly.items()):
        gross = values["revenue"] - values["cost"] - values["expense"]
        trend.append(
            {
                "period": period,
                "revenue": values["revenue"],
                "cost": values["cost"],
                "expense": values["expense"],
                "gross_profit": gross,
            }
        )
    return {**total, "trend": trend}
