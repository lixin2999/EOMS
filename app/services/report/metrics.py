"""报表指标口径唯一事实来源。

所有指标（营收/成本/现金流/利润/供应商支出/审批效率）在此定义，
API、导出与快照任务共用，避免口径漂移。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.scope import ScopeContext
from app.models.enums import DataScope
from app.models.finance import CostRecord, ProjectPnl, RevenueConfirm
from app.models.project import Project
from app.models.vendor import Contract, Vendor, VendorProject
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.utils.datetime import now, today

ZERO = Decimal("0.00")
CASH_TYPES = ("PAYMENT", "EXPENSE")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _scope(stmt: Select, ctx: ScopeContext, model: Any, *, project_attr: str = "project_id") -> Select:
    company_col = getattr(model, "company_id", None)
    if company_col is not None and not ctx.is_super:
        stmt = stmt.where(company_col == ctx.company_id)
    if ctx.is_super or ctx.has_all:
        return stmt
    branches = []
    dept_col = getattr(model, "dept_id", None)
    project_col = getattr(model, project_attr) if project_attr else None
    if ctx.dept_ids and dept_col is not None and (
        DataScope.DEPT.value in ctx.scopes or DataScope.DEPT_TREE.value in ctx.scopes
    ):
        branches.append(dept_col.in_(ctx.dept_ids))
    if DataScope.PROJECT.value in ctx.scopes and project_col is not None and ctx.project_ids:
        branches.append(project_col.in_(ctx.project_ids))
    if branches:
        return stmt.where(or_(*branches))
    # 仅 SELF 或无项目范围：按项目成员收敛，无项目则不可见
    if project_col is not None and ctx.project_ids:
        return stmt.where(project_col.in_(ctx.project_ids))
    return stmt.where(model.id == -1)


def period_range(year: int) -> tuple[str, str]:
    return f"{year}-01", f"{year}-12"


def _month_range(start: str | None, end: str | None) -> tuple[str, str]:
    current = today()
    return start or f"{current.year}-01", end or f"{current.year}-12"


def cost_totals(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    project_id: int | None = None,
) -> dict[str, Decimal]:
    start, end = _month_range(start, end)
    stmt = (
        select(CostRecord.biz_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(
            CostRecord.period >= start,
            CostRecord.period <= end,
            CostRecord.status == "ACTIVE",
            CostRecord.is_reversal.is_(False),
        )
        .group_by(CostRecord.biz_type)
    )
    if project_id:
        stmt = stmt.where(CostRecord.project_id == project_id)
    stmt = _scope(stmt, ctx, CostRecord)
    raw = {row[0]: money(row[1]) for row in db.execute(stmt).all()}
    return {
        "revenue": raw.get("RECEIVABLE", ZERO),
        "receipt": raw.get("RECEIPT", ZERO),
        "payment": raw.get("PAYMENT", ZERO),
        "expense": raw.get("EXPENSE", ZERO),
    }


def monthly_trend(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    project_id: int | None = None,
) -> list[dict]:
    start, end = _month_range(start, end)
    stmt = (
        select(CostRecord.period, CostRecord.biz_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(
            CostRecord.period >= start,
            CostRecord.period <= end,
            CostRecord.status == "ACTIVE",
            CostRecord.is_reversal.is_(False),
        )
        .group_by(CostRecord.period, CostRecord.biz_type)
        .order_by(CostRecord.period)
    )
    if project_id:
        stmt = stmt.where(CostRecord.project_id == project_id)
    stmt = _scope(stmt, ctx, CostRecord)
    buckets: dict[str, dict[str, Decimal]] = {}
    for period, biz_type, amount in db.execute(stmt).all():
        bucket = buckets.setdefault(period, {})
        bucket[biz_type] = bucket.get(biz_type, ZERO) + money(amount)
    result = []
    for period in sorted(buckets):
        bucket = buckets[period]
        revenue = bucket.get("RECEIVABLE", ZERO)
        payment = bucket.get("PAYMENT", ZERO)
        expense = bucket.get("EXPENSE", ZERO)
        cost = payment + expense
        result.append(
            {
                "period": period,
                "revenue": float(revenue),
                "payment": float(payment),
                "expense": float(expense),
                "cost": float(cost),
                "profit": float(revenue - cost),
                "receipt": float(bucket.get("RECEIPT", ZERO)),
                "cash_in": float(bucket.get("RECEIPT", ZERO)),
                "cash_out": float(payment + expense),
            }
        )
    return result


def _cashflow_by_month(
    db: Session, ctx: ScopeContext, start: str, end: str, project_id: int | None
) -> dict[str, dict[str, Decimal]]:
    stmt = (
        select(CostRecord.biz_type, CostRecord.period, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(
            CostRecord.period >= start,
            CostRecord.period <= end,
            CostRecord.status == "ACTIVE",
            CostRecord.biz_type.in_(["RECEIPT", "PAYMENT", "EXPENSE"]),
        )
        .group_by(CostRecord.biz_type, CostRecord.period)
    )
    if project_id:
        stmt = stmt.where(CostRecord.project_id == project_id)
    stmt = _scope(stmt, ctx, CostRecord)
    buckets: dict[str, dict[str, Decimal]] = {}
    for biz_type, period, amount in db.execute(stmt).all():
        bucket = buckets.setdefault(period, {})
        bucket[biz_type] = bucket.get(biz_type, ZERO) + money(amount)
    return buckets


def overview(db: Session, ctx: ScopeContext, *, year: int | None = None) -> dict:
    year = year or today().year
    start, end = period_range(year)
    totals = cost_totals(db, ctx, start=start, end=end)
    cost = totals["payment"] + totals["expense"]
    profit = totals["revenue"] - cost
    project_stmt = select(func.count(Project.id)).where(Project.status.in_(["ACTIVE", "PENDING", "SUSPENDED"]))
    project_stmt = _scope(project_stmt, ctx, Project, project_attr="id")
    project_count = int(db.execute(project_stmt).scalar_one() or 0)
    receivable_balance = totals["revenue"] - totals["receipt"]
    payable_stmt = select(
        func.coalesce(func.sum(VendorProject.contract_amount), 0),
        func.coalesce(func.sum(VendorProject.paid_amount), 0),
    )
    payable_stmt = _scope(payable_stmt, ctx, VendorProject)
    contract_amount, paid_amount = db.execute(payable_stmt).one()
    trend = monthly_trend(db, ctx, start=start, end=end)
    return {
        "year": year,
        "revenue": float(totals["revenue"]),
        "cost": float(cost),
        "payment": float(totals["payment"]),
        "expense": float(totals["expense"]),
        "gross_profit": float(profit),
        "gross_margin": round(float(profit / totals["revenue"] * 100), 2) if totals["revenue"] else 0.0,
        "receipt": float(totals["receipt"]),
        "receivable_balance": float(receivable_balance),
        "payable_balance": float(money(contract_amount) - money(paid_amount)),
        "project_count": project_count,
        "monthly": trend,
    }


def revenue_report(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    group_by: str = "period",
) -> dict:
    start, end = _month_range(start, end)
    stmt = select(
        RevenueConfirm.period,
        RevenueConfirm.project_id,
        RevenueConfirm.customer_id,
        func.coalesce(func.sum(RevenueConfirm.amount), 0),
        func.count(RevenueConfirm.id),
    ).where(
        RevenueConfirm.status == "CONFIRMED",
        RevenueConfirm.period >= start,
        RevenueConfirm.period <= end,
    )
    stmt = _scope(stmt, ctx, RevenueConfirm)
    group_column = {
        "period": RevenueConfirm.period,
        "project": RevenueConfirm.project_id,
        "customer": RevenueConfirm.customer_id,
    }.get(group_by, RevenueConfirm.period)
    stmt = stmt.group_by(group_column).order_by(group_column)
    rows = db.execute(stmt).all()
    items = []
    for period, project_id, customer_id, amount, count in rows:
        items.append(
            {
                "key": str(project_id or customer_id or period),
                "period": period,
                "project_id": project_id,
                "customer_id": customer_id,
                "amount": float(money(amount)),
                "count": int(count),
            }
        )
    total = sum(money(row[3]) for row in rows)
    return {"start": start, "end": end, "group_by": group_by, "total": float(total), "items": items}


def cashflow_report(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    project_id: int | None = None,
) -> dict:
    start, end = _month_range(start, end)
    buckets = _cashflow_by_month(db, ctx, start, end, project_id)
    rows = []
    cumulative = ZERO
    for period in sorted(buckets):
        bucket = buckets[period]
        inflow = bucket.get("RECEIPT", ZERO)
        outflow = bucket.get("PAYMENT", ZERO) + bucket.get("EXPENSE", ZERO)
        net = inflow - outflow
        cumulative += net
        rows.append(
            {
                "period": period,
                "inflow": float(inflow),
                "outflow": float(outflow),
                "net": float(net),
                "cumulative": float(cumulative),
            }
        )
    return {
        "start": start,
        "end": end,
        "total_inflow": float(sum(money(row["inflow"]) for row in rows)),
        "total_outflow": float(sum(money(row["outflow"]) for row in rows)),
        "net": float(sum(money(row["net"]) for row in rows)),
        "items": rows,
    }


def profit_report(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    project_id: int | None = None,
    group_by: str = "period",
) -> dict:
    start, end = _month_range(start, end)
    trend = monthly_trend(db, ctx, start=start, end=end, project_id=project_id)
    revenue = sum(money(row["revenue"]) for row in trend)
    cost = sum(money(row["cost"]) for row in trend)
    profit = revenue - cost
    if group_by == "project":
        stmt = (
            select(
                CostRecord.project_id,
                CostRecord.biz_type,
                func.coalesce(func.sum(CostRecord.amount), 0),
            )
            .where(
                CostRecord.period >= start,
                CostRecord.period <= end,
                CostRecord.status == "ACTIVE",
            )
            .group_by(CostRecord.project_id, CostRecord.biz_type)
        )
        if project_id:
            stmt = stmt.where(CostRecord.project_id == project_id)
        stmt = _scope(stmt, ctx, CostRecord)
        grouped: dict[int | None, dict[str, Decimal]] = {}
        for pid, biz_type, amount in db.execute(stmt).all():
            grouped.setdefault(pid, {})[biz_type] = money(amount)
        detail = []
        for pid, values in grouped.items():
            item_revenue = values.get("RECEIVABLE", ZERO)
            item_cost = values.get("PAYMENT", ZERO) + values.get("EXPENSE", ZERO)
            detail.append(
                {
                    "project_id": pid,
                    "revenue": float(item_revenue),
                    "cost": float(item_cost),
                    "profit": float(item_revenue - item_cost),
                    "margin": round(float((item_revenue - item_cost) / item_revenue * 100), 2) if item_revenue else 0.0,
                }
            )
        detail.sort(key=lambda item: item["profit"] or 0.0, reverse=True)
    else:
        detail = trend
    return {
        "start": start,
        "end": end,
        "revenue": float(revenue),
        "cost": float(cost),
        "profit": float(profit),
        "margin": round(float(profit / revenue * 100), 2) if revenue else 0.0,
        "items": detail,
    }


def project_pnl_report(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
    project_id: int | None = None,
) -> dict:
    start, end = _month_range(start, end)
    stmt = select(ProjectPnl).where(ProjectPnl.period >= start, ProjectPnl.period <= end)
    if project_id:
        stmt = stmt.where(ProjectPnl.project_id == project_id)
    stmt = _scope(stmt, ctx, ProjectPnl)
    rows = list(db.execute(stmt.order_by(ProjectPnl.period, ProjectPnl.project_id)).scalars().all())
    if not rows:
        # 快照尚未生成时回退实时聚合
        return profit_report(db, ctx, start=start, end=end, project_id=project_id, group_by="project")
    # 快照为「截至当期」的累计口径，同一项目只取区间内最新一期，避免重复累计
    latest: dict[int, ProjectPnl] = {}
    for item in rows:
        current = latest.get(item.project_id)
        if current is None or (item.period, item.id) > (current.period, current.id):
            latest[item.project_id] = item
    rows = [latest[key] for key in sorted(latest)]
    project_map = {
        item.id: item
        for item in db.execute(select(Project).where(Project.id.in_(list(latest)))).scalars().all()
    }
    return {
        "start": start,
        "end": end,
        "items": [
            {
                "project_id": item.project_id,
                "project_no": project_map[item.project_id].no if item.project_id in project_map else "",
                "project_name": project_map[item.project_id].name if item.project_id in project_map else "",
                "dept_id": item.dept_id,
                "period": item.period,
                "revenue": float(item.revenue),
                "cost": float(item.cost),
                "expense": float(item.expense),
                "gross_profit": float(item.gross_profit),
                "gross_margin": float(item.gross_margin),
                "budget_amount": float(item.budget_amount),
                "cost_variance": float(item.cost_variance),
                "milestone_rate": float(item.milestone_rate),
            }
            for item in rows
        ],
    }


def vendor_spend_report(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    start, end = _month_range(start, end)
    stmt = (
        select(
            CostRecord.vendor_id,
            func.coalesce(func.sum(CostRecord.amount), 0),
            func.count(CostRecord.id),
        )
        .where(
            CostRecord.period >= start,
            CostRecord.period <= end,
            CostRecord.status == "ACTIVE",
            CostRecord.biz_type.in_(["PAYMENT", "EXPENSE"]),
            CostRecord.vendor_id.is_not(None),
        )
        .group_by(CostRecord.vendor_id)
    )
    stmt = _scope(stmt, ctx, CostRecord)
    spend = {vendor_id: (money(amount), int(count)) for vendor_id, amount, count in db.execute(stmt).all()}
    vendor_ids = list(spend)
    vendors = {
        vendor.id: vendor
        for vendor in db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids))).scalars().all()
    } if vendor_ids else {}
    contract_rows = db.execute(
        select(Contract.vendor_id, func.coalesce(func.sum(Contract.amount), 0))
        .where(Contract.vendor_id.in_(vendor_ids))
        .group_by(Contract.vendor_id)
    ).all() if vendor_ids else []
    contracts = {vendor_id: money(amount) for vendor_id, amount in contract_rows}
    items = []
    total = sum(value[0] for value in spend.values())
    for vendor_id, (amount, count) in spend.items():
        vendor = vendors.get(vendor_id)
        items.append(
            {
                "vendor_id": vendor_id,
                "vendor_name": vendor.name if vendor else f"供应商#{vendor_id}",
                "level": vendor.level if vendor else "",
                "score": float(vendor.score or 0) if vendor else 0.0,
                "spend": float(amount),
                "count": count,
                "contract_amount": float(contracts.get(vendor_id, ZERO)),
                "ratio": round(float(amount / total * 100), 2) if total else 0.0,
            }
        )
    items.sort(key=lambda item: item["spend"], reverse=True)
    return {"start": start, "end": end, "total": float(total), "items": items}


def approval_efficiency(
    db: Session,
    ctx: ScopeContext,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    start, end = _month_range(start, end)
    stmt = select(WorkflowInstance).where(
        WorkflowInstance.start_at >= date(int(start[:4]), int(start[5:7]), 1)
    )
    stmt = _scope(stmt, ctx, WorkflowInstance)
    instances = list(db.execute(stmt).scalars().all())
    instances = [
        item
        for item in instances
        if item.start_at.strftime("%Y-%m") <= end
    ]
    instance_ids = [item.id for item in instances]
    tasks = (
        list(
            db.execute(select(WorkflowTask).where(WorkflowTask.instance_id.in_(instance_ids))).scalars().all()
        )
        if instance_ids
        else []
    )
    now_ts = now()
    by_type: dict[str, dict] = {}
    for instance in instances:
        bucket = by_type.setdefault(
            instance.biz_type,
            {
                "biz_type": instance.biz_type,
                "total": 0,
                "approved": 0,
                "rejected": 0,
                "hours": Decimal("0"),
                "overdue": 0,
            },
        )
        bucket["total"] += 1
        if instance.status == "APPROVED":
            bucket["approved"] += 1
        elif instance.status == "REJECTED":
            bucket["rejected"] += 1
        if instance.finish_at:
            delta = instance.finish_at - instance.start_at
            bucket["hours"] += Decimal(str(delta.total_seconds())) / Decimal(3600)
    task_by_instance: dict[int, list[WorkflowTask]] = {}
    for task in tasks:
        task_by_instance.setdefault(task.instance_id, []).append(task)
    instance_type = {item.id: item.biz_type for item in instances}
    for task in tasks:
        overdue_pending = task.status == "PENDING" and task.due_at and task.due_at < now_ts
        overdue_done = task.finish_at and task.due_at and task.finish_at > task.due_at
        if overdue_pending or overdue_done:
            type_bucket = by_type.get(instance_type.get(task.instance_id, ""))
            if type_bucket:
                type_bucket["overdue"] += 1
    items = []
    for bucket in by_type.values():
        finished = bucket["approved"] + bucket["rejected"]
        total = bucket["total"]
        items.append(
            {
                "biz_type": bucket["biz_type"],
                "total": total,
                "approved": bucket["approved"],
                "rejected": bucket["rejected"],
                "avg_hours": round(float(bucket["hours"] / finished), 2) if finished else 0.0,
                "reject_rate": round(bucket["rejected"] / finished * 100, 2) if finished else 0.0,
                "overdue_tasks": bucket["overdue"],
                "overdue_rate": round(bucket["overdue"] / max(len(tasks), 1) * 100, 2),
            }
        )
    items.sort(key=lambda item: item["total"], reverse=True)
    return {
        "start": start,
        "end": end,
        "total_instances": len(instances),
        "avg_hours": round(
            sum(item["avg_hours"] * max(item["approved"] + item["rejected"], 0) for item in items)
            / max(sum(item["approved"] + item["rejected"] for item in items), 1),
            2,
        ),
        "items": items,
    }
