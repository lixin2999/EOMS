"""财务：成本台账、付款、收款、计收、预算、期间与科目。"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import User
from app.models.project import Project
from app.models.vendor import Contract, Vendor
from app.schemas.common import (
    BudgetIn,
    PayIn,
    PaymentIn,
    PeriodIn,
    ReceiptIn,
    RevenueIn,
    ReverseIn,
)
from app.services.cost import accounts as account_service
from app.services.cost import budget as budget_service
from app.services.cost import budget_admin as budget_admin_service
from app.services.cost import cost as cost_service
from app.services.cost import payment as payment_service
from app.services.cost import period as period_service
from app.services.cost import receipt as receipt_service
from app.services.cost import revenue as revenue_service
from app.services.report import pnl as pnl_service

router = APIRouter(prefix="/finance", tags=["财务管理"])

VIEW = Depends(require_permission("finance:view"))
COST = Depends(require_permission("finance:cost"))
PAYMENT = Depends(require_permission("finance:payment"))
RECEIPT = Depends(require_permission("finance:receipt"))
REVENUE = Depends(require_permission("finance:revenue"))
BUDGET = Depends(require_permission("finance:budget"))
PERIOD = Depends(require_permission("finance:period"))


# ------------------------------------------------------------------ 序列化辅助
def _names(db, user_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in user_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.real_name).where(User.id.in_(ids))).all()
    return {int(uid): name for uid, name in rows}


def _projects(db, project_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in project_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Project.id, Project.name).where(Project.id.in_(ids))).all()
    return {int(pid): name for pid, name in rows}


def _vendors(db, vendor_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in vendor_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Vendor.id, Vendor.name).where(Vendor.id.in_(ids))).all()
    return {int(vid): name for vid, name in rows}


def _contracts(db, contract_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in contract_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Contract.id, Contract.no).where(Contract.id.in_(ids))).all()
    return {int(cid): no for cid, no in rows}


def _with_project(data: dict, project_id: int | None, projects: dict[int, str]) -> dict:
    data["project_name"] = projects.get(project_id or 0, "")
    return data


def _num(value):
    return float(value) if isinstance(value, Decimal) else value


# ------------------------------------------------------------------ 成本台账
@router.get("/costs", summary="成本记录列表", dependencies=[VIEW])
def list_costs(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    project_id: int | None = None,
    biz_type: str | None = None,
    period: str | None = None,
    account_code: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    from app.utils.datetime import to_date

    result = cost_service.list_costs(
        db,
        ctx,
        params,
        project_id=project_id,
        biz_type=biz_type,
        period=period,
        account_code=account_code,
        keyword=keyword,
        date_from=to_date(date_from),
        date_to=to_date(date_to),
    )
    projects = _projects(db, (item.project_id for item in result["items"]))
    vendors = _vendors(db, (item.vendor_id for item in result["items"] if item.vendor_id))
    items = []
    for row in result["items"]:
        data = _with_project(to_dict(row), row.project_id, projects)
        data["vendor_name"] = vendors.get(row.vendor_id or 0, "")
        items.append(data)
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "totals": {key: float(value) for key, value in result.get("totals", {}).items()},
        }
    )


@router.get("/costs/{cost_id}", summary="成本记录详情", dependencies=[VIEW])
def get_cost(cost_id: int, db: DbSession, ctx: Scope) -> dict:
    row = cost_service.get_cost(db, ctx, cost_id)
    data = _with_project(to_dict(row), row.project_id, _projects(db, [row.project_id]))
    data["vendor_name"] = _vendors(db, [row.vendor_id] if row.vendor_id else []).get(
        row.vendor_id or 0, ""
    )
    return ok(data)


@router.post("/costs/{cost_id}/reverse", summary="冲销成本记录", dependencies=[COST])
def reverse_cost(cost_id: int, payload: ReverseIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    record = cost_service.reverse(db, user, ctx, cost_id, payload.reason)
    return ok(to_dict(record), "成本记录已冲销")


# ------------------------------------------------------------------ 付款
@router.get("/payments", summary="付款单列表", dependencies=[VIEW])
def list_payments(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    project_id: int | None = None,
    vendor_id: int | None = None,
    status: str | None = None,
) -> dict:
    result = payment_service.list_payments(
        db, ctx, params, project_id=project_id, vendor_id=vendor_id, status=status
    )
    projects = _projects(db, (item.project_id for item in result["items"]))
    vendors = _vendors(db, (item.vendor_id for item in result["items"] if item.vendor_id))
    names = _names(db, (item.applicant_id for item in result["items"]))
    items = []
    for row in result["items"]:
        data = _with_project(to_dict(row), row.project_id, projects)
        data["vendor_name"] = vendors.get(row.vendor_id or 0, "")
        data["applicant_name"] = names.get(row.applicant_id, "")
        items.append(data)
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("/payments", summary="新建付款单", dependencies=[PAYMENT])
def create_payment(payload: PaymentIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = payment_service.create_payment(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "付款单已创建")


@router.get("/payments/{payment_id}", summary="付款单详情", dependencies=[VIEW])
def get_payment(payment_id: int, db: DbSession, ctx: Scope) -> dict:
    row = payment_service.get_payment(db, ctx, payment_id)
    data = _with_project(to_dict(row), row.project_id, _projects(db, [row.project_id]))
    data["vendor_name"] = _vendors(db, [row.vendor_id] if row.vendor_id else []).get(
        row.vendor_id or 0, ""
    )
    data["contract_no"] = _contracts(db, [row.contract_id] if row.contract_id else []).get(
        row.contract_id or 0, ""
    )
    return ok(data)


@router.post("/payments/{payment_id}/pay", summary="执行付款", dependencies=[PAYMENT])
def pay_payment(payment_id: int, payload: PayIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = payment_service.pay_payment(db, user, ctx, payment_id, payload.pay_date)
    return ok(to_dict(row), "付款已完成")


@router.post("/payments/{payment_id}/cancel", summary="取消付款单", dependencies=[PAYMENT])
def cancel_payment(payment_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = payment_service.cancel_payment(db, user, ctx, payment_id)
    return ok(to_dict(row), "付款单已取消")


# ------------------------------------------------------------------ 收款
@router.get("/receipts", summary="收款单列表", dependencies=[VIEW])
def list_receipts(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    project_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    from app.utils.datetime import to_date

    result = receipt_service.list_receipts(
        db, ctx, params, project_id=project_id, date_from=to_date(date_from), date_to=to_date(date_to)
    )
    projects = _projects(db, (item.project_id for item in result["items"]))
    items = [_with_project(to_dict(row), row.project_id, projects) for row in result["items"]]
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("/receipts", summary="登记收款", dependencies=[RECEIPT])
def create_receipt(payload: ReceiptIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = receipt_service.create_receipt(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "收款已登记")


@router.get("/receipts/{receipt_id}", summary="收款单详情", dependencies=[VIEW])
def get_receipt(receipt_id: int, db: DbSession, ctx: Scope) -> dict:
    row = receipt_service.get_receipt(db, ctx, receipt_id)
    return ok(_with_project(to_dict(row), row.project_id, _projects(db, [row.project_id])))


@router.post("/receipts/{receipt_id}/cancel", summary="作废收款", dependencies=[RECEIPT])
def cancel_receipt(receipt_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = receipt_service.cancel_receipt(db, user, ctx, receipt_id)
    return ok(to_dict(row), "收款已作废并冲销")


# ------------------------------------------------------------------ 计收
@router.get("/revenue", summary="计收单列表", dependencies=[VIEW])
def list_revenue(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    project_id: int | None = None,
    period: str | None = None,
    status: str | None = None,
) -> dict:
    result = revenue_service.list_revenue(
        db, ctx, params, project_id=project_id, period=period, status=status
    )
    projects = _projects(db, (item.project_id for item in result["items"]))
    items = [_with_project(to_dict(row), row.project_id, projects) for row in result["items"]]
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("/revenue", summary="新增计收（可自动确认）", dependencies=[REVENUE])
def create_revenue(payload: RevenueIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = revenue_service.create_revenue(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "计收单已创建")


@router.get("/revenue/{revenue_id}", summary="计收单详情", dependencies=[VIEW])
def get_revenue(revenue_id: int, db: DbSession, ctx: Scope) -> dict:
    row = revenue_service.get_revenue(db, ctx, revenue_id)
    return ok(_with_project(to_dict(row), row.project_id, _projects(db, [row.project_id])))


@router.post("/revenue/{revenue_id}/confirm", summary="确认计收", dependencies=[REVENUE])
def confirm_revenue(revenue_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = revenue_service.confirm_revenue(db, user, ctx, revenue_id)
    return ok(to_dict(row), "计收已确认")


@router.post("/revenue/{revenue_id}/cancel", summary="取消计收", dependencies=[REVENUE])
def cancel_revenue(revenue_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = revenue_service.cancel_revenue(db, user, ctx, revenue_id)
    return ok(to_dict(row), "计收已取消并冲销")


# ------------------------------------------------------------------ 预算
@router.get("/budgets", summary="项目预算与执行", dependencies=[BUDGET])
def list_budgets(
    project_id: int,
    db: DbSession,
    ctx: Scope,
    year: int | None = None,
) -> dict:
    result = budget_admin_service.list_budgets(db, ctx, project_id, year)
    return ok(
        {
            "items": [to_dict(row) for row in result["items"]],
            "status": {
                key: _num(value)
                for key, value in (result["status"] or {}).items()
                if key != "rows"
            }
            if result.get("status")
            else None,
            "rows": [
                {key: _num(value) for key, value in row.items()}
                for row in (result.get("status") or {}).get("rows", [])
            ],
        }
    )


@router.post("/budgets", summary="保存项目预算", dependencies=[BUDGET])
def save_budget(payload: BudgetIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = budget_admin_service.save_budget(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "预算已保存")


@router.delete("/budgets/{budget_id}", summary="删除项目预算", dependencies=[BUDGET])
def delete_budget(budget_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    budget_admin_service.delete_budget(db, user, ctx, budget_id)
    return ok(None, "预算已删除")


@router.get("/budget-status", summary="预算执行状态", dependencies=[BUDGET])
def budget_status(project_id: int, db: DbSession, ctx: Scope, year: int | None = None) -> dict:
    from app.core.errors import NotFoundError
    from app.models.project import Project
    from app.services.cost.budget import budget_status as _status

    project = db.get(Project, project_id)
    if project is None or project.company_id != ctx.company_id:
        raise NotFoundError("项目不存在")
    data = _status(db, project_id, year)
    return ok(
        {
            "year": data["year"],
            "total_budget": float(data["total_budget"]),
            "total_actual": float(data["total_actual"]),
            "rate": data["rate"],
            "generated_at": data["generated_at"],
            "rows": [
                {
                    "account_code": row["account_code"],
                    "budget": float(row["budget"]),
                    "actual": float(row["actual"]),
                    "rate": row["rate"],
                    "alert": row["alert"],
                }
                for row in data["rows"]
            ],
        }
    )


# ------------------------------------------------------------------ 期间 / 科目
@router.get("/periods", summary="会计期间", dependencies=[PERIOD])
def list_periods(db: DbSession, ctx: Scope, year: int | None = None) -> dict:
    rows = period_service.list_periods(db, ctx.company_id, year)
    return ok([to_dict(row) for row in rows])


@router.post("/periods/close", summary="关账", dependencies=[PERIOD])
def close_period(payload: PeriodIn, db: DbSession, user: CurrentUser) -> dict:
    row = period_service.close_period(db, user, payload.period, payload.remark)
    return ok(to_dict(row), f"期间 {payload.period} 已关账")


@router.post("/periods/reopen", summary="反关账", dependencies=[PERIOD])
def reopen_period(payload: PeriodIn, db: DbSession, user: CurrentUser) -> dict:
    row = period_service.reopen_period(db, user, payload.period, payload.remark or "")
    return ok(to_dict(row), f"期间 {payload.period} 已反关账")


@router.get("/accounts", summary="费用科目", dependencies=[VIEW])
def list_accounts(db: DbSession, ctx: Scope) -> dict:
    rows = budget_admin_service.list_accounts(db, ctx)
    return ok(
        [
            {**to_dict(row), "default_name": account_service.ACCOUNT_NAMES.get(row.code, row.name)}
            for row in rows
        ]
    )


# ------------------------------------------------------------------ 项目成本 / 损益
@router.get("/projects/{project_id}/summary", summary="项目成本汇总", dependencies=[VIEW])
def project_cost_summary(project_id: int, db: DbSession, ctx: Scope) -> dict:
    data = cost_service.project_cost_summary(db, ctx, project_id)
    return ok({key: _num(value) for key, value in data.items()})


@router.get("/projects/{project_id}/pnl", summary="项目损益（含月度趋势）", dependencies=[VIEW])
def project_pnl(project_id: int, db: DbSession, ctx: Scope) -> dict:
    return ok(pnl_service.project_pnl_detail(db, ctx, project_id))


@router.get("/projects/{project_id}/budget", summary="项目预算总览", dependencies=[BUDGET])
def project_budget(project_id: int, db: DbSession, ctx: Scope, year: int | None = None) -> dict:
    from app.utils.datetime import today

    data = budget_service.budget_status(db, project_id, year or today().year)
    return ok(
        {
            "year": data["year"],
            "total_budget": float(data["total_budget"]),
            "total_actual": float(data["total_actual"]),
            "rate": data["rate"],
            "rows": [
                {
                    "account_code": row["account_code"],
                    "budget": float(row["budget"]),
                    "actual": float(row["actual"]),
                    "rate": row["rate"],
                    "alert": row["alert"],
                }
                for row in data["rows"]
            ],
        }
    )
