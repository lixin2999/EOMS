"""报表编排、快照落库与查询。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext
from app.models.enums import PeriodStatus, ReportCode
from app.models.finance import Period
from app.models.iam import Company
from app.models.report import ReportSnapshot
from app.services.report import metrics
from app.utils.datetime import now, period_of, today

REPORT_LABELS = {
    "OVERVIEW": "经营总览",
    "REVENUE": "营收报表",
    "CASHFLOW": "现金流量表",
    "PROFIT": "利润表",
    "PROJECT_PNL": "项目损益表",
    "VENDOR_SPEND": "供应商支出分析",
    "APPROVAL_EFFICIENCY": "审批效率报表",
}


def build_report(
    db: Session,
    ctx: ScopeContext,
    code: str,
    *,
    start: str | None = None,
    end: str | None = None,
    group_by: str | None = None,
    project_id: int | None = None,
    year: int | None = None,
) -> dict:
    code = code.upper()
    snapshot = _snapshot_payload(
        db, ctx, code, start=start, end=end, year=year, project_id=project_id, group_by=group_by
    )
    if snapshot is not None:
        return snapshot
    if code == ReportCode.OVERVIEW.value:
        result = metrics.overview(db, ctx, year=year)
    elif code == ReportCode.REVENUE.value:
        result = metrics.revenue_report(db, ctx, start=start, end=end, group_by=group_by or "period")
    elif code == ReportCode.CASHFLOW.value:
        result = metrics.cashflow_report(db, ctx, start=start, end=end, project_id=project_id)
    elif code == ReportCode.PROFIT.value:
        result = metrics.profit_report(
            db, ctx, start=start, end=end, project_id=project_id, group_by=group_by or "period"
        )
    elif code == ReportCode.PROJECT_PNL.value:
        result = metrics.project_pnl_report(db, ctx, start=start, end=end, project_id=project_id)
    elif code == ReportCode.VENDOR_SPEND.value:
        result = metrics.vendor_spend_report(db, ctx, start=start, end=end)
    elif code == ReportCode.APPROVAL_EFFICIENCY.value:
        result = metrics.approval_efficiency(db, ctx, start=start, end=end)
    else:
        raise BusinessRuleError("未知报表编码")
    # meta 为 dict，导出时会被 _scalar_rows 自动跳过。
    result["meta"] = {"source": "REALTIME"}
    return result


def _snapshot_payload(
    db: Session,
    ctx: ScopeContext,
    code: str,
    *,
    start: str | None = None,
    end: str | None = None,
    year: int | None = None,
    project_id: int | None = None,
    group_by: str | None = None,
) -> dict | None:
    """命中已关账期间的公司级快照时直接复用，保证报表口径与关账一致。

    仅当维度可对齐快照时才命中：无项目筛选、按月分组、单月区间且该期间已关账；
    ``OVERVIEW`` 按年度口径，要求快照 ``payload.year`` 与目标年度一致。
    """
    if project_id is not None or group_by not in (None, "period"):
        return None
    base = select(ReportSnapshot).where(
        ReportSnapshot.company_id == ctx.company_id,
        ReportSnapshot.report_code == code,
        ReportSnapshot.dim_type == "COMPANY",
        ReportSnapshot.dim_value == "0",
    )
    target_year = year or today().year
    if code == ReportCode.OVERVIEW.value:
        if year is not None and year != today().year:
            return None
        item = db.execute(base.order_by(ReportSnapshot.period.desc()).limit(1)).scalar_one_or_none()
        if item is None:
            return None
        payload = dict(item.payload or {})
        if int(payload.get("year") or 0) != target_year:
            return None
        return {
            **payload,
            "meta": {"source": "SNAPSHOT", "period": item.period, "version": item.version},
        }

    if not start or not end or start != end or len(start) != 7 or start[4] != "-":
        return None
    closed = db.execute(
        select(Period.id).where(
            Period.company_id == ctx.company_id,
            Period.period == start,
            Period.status == PeriodStatus.CLOSED.value,
        )
    ).scalar_one_or_none()
    if closed is None:
        return None
    item = db.execute(
        base.where(ReportSnapshot.period == start).limit(1)
    ).scalar_one_or_none()
    if item is None:
        return None
    return {
        **dict(item.payload or {}),
        "meta": {"source": "SNAPSHOT", "period": start, "version": item.version},
    }


def _snapshot_period(period: str | None) -> str:
    if not period:
        return period_of(today())
    if len(period) != 7 or period[4] != "-":
        raise BusinessRuleError("期间格式应为 YYYY-MM")
    return period


def upsert_snapshot(
    db: Session,
    *,
    company_id: int,
    report_code: str,
    period: str,
    dim_type: str = "COMPANY",
    dim_value: str = "0",
    payload: dict,
) -> ReportSnapshot:
    item = db.execute(
        select(ReportSnapshot).where(
            ReportSnapshot.company_id == company_id,
            ReportSnapshot.report_code == report_code,
            ReportSnapshot.period == period,
            ReportSnapshot.dim_type == dim_type,
            ReportSnapshot.dim_value == dim_value,
        )
    ).scalar_one_or_none()
    if item is None:
        item = ReportSnapshot(
            company_id=company_id,
            report_code=report_code,
            period=period,
            dim_type=dim_type,
            dim_value=dim_value,
            payload=payload,
            version=1,
            generated_at=now(),
        )
        db.add(item)
    else:
        item.payload = payload
        item.version = int(item.version or 1) + 1
        item.generated_at = now()
    db.flush()
    return item


def generate_company_snapshots(db: Session, company_id: int, period: str | None = None) -> dict:
    """按公司生成报表快照（Celery 定时任务调用），使用系统级 Scope。"""
    from app.core.scope import ScopeContext

    period = _snapshot_period(period)
    ctx = ScopeContext(user_id=0, company_id=company_id, dept_id=None, is_super=True, scopes={"ALL"})
    start = end = period
    payloads = {
        ReportCode.OVERVIEW.value: metrics.overview(db, ctx, year=int(period[:4])),
        ReportCode.REVENUE.value: metrics.revenue_report(db, ctx, start=start, end=end),
        ReportCode.CASHFLOW.value: metrics.cashflow_report(db, ctx, start=start, end=end),
        ReportCode.PROFIT.value: metrics.profit_report(db, ctx, start=start, end=end),
        ReportCode.PROJECT_PNL.value: metrics.project_pnl_report(db, ctx, start=start, end=end),
        ReportCode.VENDOR_SPEND.value: metrics.vendor_spend_report(db, ctx, start=start, end=end),
        ReportCode.APPROVAL_EFFICIENCY.value: metrics.approval_efficiency(db, ctx, start=start, end=end),
    }
    count = 0
    for code, payload in payloads.items():
        upsert_snapshot(db, company_id=company_id, report_code=code, period=period, payload=payload)
        count += 1
    return {"company_id": company_id, "period": period, "count": count}


def generate_all_snapshots(db: Session, period: str | None = None) -> dict:
    companies = list(db.execute(select(Company).where(Company.status == "ACTIVE")).scalars().all())
    total = 0
    for company in companies:
        total += generate_company_snapshots(db, company.id, period)["count"]
    return {"companies": len(companies), "count": total, "period": _snapshot_period(period)}


def list_snapshots(
    db: Session, ctx: ScopeContext, *, report_code: str | None = None, limit: int = 30
) -> list[ReportSnapshot]:
    stmt = select(ReportSnapshot).where(ReportSnapshot.company_id == ctx.company_id)
    if report_code:
        stmt = stmt.where(ReportSnapshot.report_code == report_code.upper())
    stmt = stmt.order_by(ReportSnapshot.period.desc(), ReportSnapshot.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_snapshot(db: Session, ctx: ScopeContext, report_code: str, period: str | None = None) -> ReportSnapshot:
    stmt = select(ReportSnapshot).where(
        ReportSnapshot.company_id == ctx.company_id, ReportSnapshot.report_code == report_code.upper()
    )
    if period:
        stmt = stmt.where(ReportSnapshot.period == period)
    item = db.execute(stmt.order_by(ReportSnapshot.period.desc()).limit(1)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("报表快照尚未生成")
    return item
