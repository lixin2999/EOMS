"""首页驾驶舱。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.response import ok
from app.core.deps import CurrentUser, DbSession, Scope
from app.services import dashboard as dashboard_service
from app.services.report import metrics
from app.utils.datetime import today

router = APIRouter(prefix="/dashboard", tags=["首页驾驶舱"])


@router.get("", summary="驾驶舱聚合数据")
def get_dashboard(db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    return ok(dashboard_service.dashboard(db, ctx))


@router.get("/overview", summary="经营概览")
def overview(db: DbSession, user: CurrentUser, ctx: Scope, year: int | None = None) -> dict:
    return ok(metrics.overview(db, ctx, year=year or today().year))


@router.get("/health", summary="项目健康度（含延期）")
def project_health(db: DbSession, user: CurrentUser, ctx: Scope, limit: int = 10) -> dict:
    return ok(dashboard_service.project_health(db, ctx, limit=max(1, min(limit, 50))))


@router.get("/alerts", summary="证照/合同到期提醒")
def alerts(db: DbSession, user: CurrentUser, ctx: Scope, days: int = 45) -> dict:
    from app.services.vendor.contract import contract_risks
    from app.services.vendor.vendor import vendor_risks

    return ok(
        {
            "licenses": dashboard_service.license_alerts(db, ctx.company_id, days),
            "vendors": vendor_risks(db, ctx),
            "contracts": contract_risks(db, ctx, warning_days=days),
        }
    )
