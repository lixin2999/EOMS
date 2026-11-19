"""报表编排、快照落库与查询。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext
from app.models.enums import ReportCode
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
    if code == ReportCode.OVERVIEW.value:
        return metrics.overview(db, ctx, year=year)
    if code == ReportCode.REVENUE.value:
        return metrics.revenue_report(db, ctx, start=start, end=end, group_by=group_by or "period")
    if code == ReportCode.CASHFLOW.value:
        return metrics.cashflow_report(db, ctx, start=start, end=end, project_id=project_id)
    if code == ReportCode.PROFIT.value:
        return metrics.profit_report(
            db, ctx, start=start, end=end, project_id=project_id, group_by=group_by or "period"
        )
    if code == ReportCode.PROJECT_PNL.value:
        return metrics.project_pnl_report(db, ctx, start=start, end=end, project_id=project_id)
    if code == ReportCode.VENDOR_SPEND.value:
        return metrics.vendor_spend_report(db, ctx, start=start, end=end)
    if code == ReportCode.APPROVAL_EFFICIENCY.value:
        return metrics.approval_efficiency(db, ctx, start=start, end=end)
    raise BusinessRuleError("未知报表编码")


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
