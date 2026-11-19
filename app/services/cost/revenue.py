from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.enums import RevenueStatus
from app.models.finance import CostRecord, RevenueConfirm
from app.models.iam import User
from app.models.project import Project
from app.services.common import company_code
from app.services.cost.ledger import record_cost, reverse_cost
from app.services.iam.audit import snapshot, write_audit
from app.services.project.project import get_project
from app.utils.datetime import now, period_of, to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import next_no

REVENUE_ACCOUNT = "6001"


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(RevenueConfirm)
    condition = scope_condition(ctx, RevenueConfirm)
    return stmt.where(condition) if condition is not None else stmt


def list_revenue(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    project_id: int | None = None,
    period: str | None = None,
    status: str | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if project_id:
        stmt = stmt.where(RevenueConfirm.project_id == project_id)
    if period:
        stmt = stmt.where(RevenueConfirm.period == period)
    if status:
        stmt = stmt.where(RevenueConfirm.status == status)
    stmt = stmt.order_by(RevenueConfirm.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_revenue(db: Session, ctx: ScopeContext, revenue_id: int) -> RevenueConfirm:
    item = db.execute(_base_query(ctx).where(RevenueConfirm.id == revenue_id)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("计收单不存在或无权访问")
    return item


def create_revenue(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> RevenueConfirm:
    project = get_project(db, ctx, int(payload.get("project_id") or 0))
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增计收")
    amount = to_decimal(payload.get("amount"), field_name="计收金额")
    if amount <= 0:
        raise BusinessRuleError("计收金额必须大于 0")
    confirm_date = to_date(payload.get("confirm_date")) or today()
    item = RevenueConfirm(
        company_id=user.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=user.id,
        no=next_no(db, "REV", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        customer_id=payload.get("customer_id") or project.customer_id,
        contract_id=payload.get("contract_id"),
        amount=amount,
        currency=str(payload.get("currency") or "CNY")[:8],
        confirm_date=confirm_date,
        period=period_of(confirm_date),
        source_type="MANUAL",
        source_id=None,
        status=RevenueStatus.DRAFT.value,
        remark=(payload.get("remark") or "")[:1000],
    )
    db.add(item)
    db.flush()
    write_audit(
        db, user=user, action="CREATE_REVENUE", target_type="REVENUE", target_id=item.id, after=snapshot(item)
    )
    if payload.get("confirm", True):
        confirm_revenue(db, user, ctx, item.id)
    return item


def confirm_revenue(db: Session, user: User, ctx: ScopeContext, revenue_id: int) -> RevenueConfirm:
    item = get_revenue(db, ctx, revenue_id)
    if item.status != RevenueStatus.DRAFT.value:
        raise BusinessRuleError("仅草稿状态可确认计收")
    item.status = RevenueStatus.CONFIRMED.value
    db.flush()
    record_cost(
        db,
        company_id=item.company_id,
        dept_id=item.dept_id,
        project_id=item.project_id,
        biz_type="RECEIVABLE",
        biz_id=item.id,
        account_code=REVENUE_ACCOUNT,
        amount=Decimal(str(item.amount)),
        occur_date=item.confirm_date,
        currency=item.currency,
        applicant_id=item.creator_id,
        source_no=item.no,
    )
    write_audit(db, user=user, action="CONFIRM_REVENUE", target_type="REVENUE", target_id=item.id)
    return item


def cancel_revenue(db: Session, user: User, ctx: ScopeContext, revenue_id: int) -> RevenueConfirm:
    item = get_revenue(db, ctx, revenue_id)
    if item.status == RevenueStatus.CANCELED.value:
        return item
    if item.status == RevenueStatus.CONFIRMED.value:
        records = db.execute(
            select(CostRecord).where(
                CostRecord.biz_type == "RECEIVABLE",
                CostRecord.biz_id == item.id,
                CostRecord.status == "ACTIVE",
            )
        ).scalars()
        for record in records:
            reverse_cost(db, record.id, user, "计收取消冲销")
    item.status = RevenueStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_REVENUE", target_type="REVENUE", target_id=item.id)
    return item


def auto_from_acceptance(
    db: Session, project_id: int, acceptance_id: int, amount: Decimal, accept_date
) -> RevenueConfirm | None:
    if amount <= 0:
        return None
    existing = db.execute(
        select(RevenueConfirm).where(
            RevenueConfirm.source_type == "ACCEPTANCE", RevenueConfirm.source_id == acceptance_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    project = db.get(Project, project_id)
    if project is None:
        return None
    item = RevenueConfirm(
        company_id=project.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=project.manager_id,
        no=next_no(db, "REV", company_code=company_code(db, project.company_id), period=now().strftime("%Y%m")),
        customer_id=project.customer_id,
        contract_id=None,
        amount=amount,
        currency="CNY",
        confirm_date=accept_date,
        period=period_of(accept_date),
        source_type="ACCEPTANCE",
        source_id=acceptance_id,
        status=RevenueStatus.CONFIRMED.value,
        remark="项目验收自动计收",
    )
    db.add(item)
    db.flush()
    # 期间已关账时验收自动计收不影响验收动作：成本转入待补记，开账后补记。
    record_cost(
        db,
        company_id=item.company_id,
        dept_id=item.dept_id,
        project_id=item.project_id,
        biz_type="RECEIVABLE",
        biz_id=item.id,
        account_code=REVENUE_ACCOUNT,
        amount=Decimal(str(item.amount)),
        occur_date=item.confirm_date,
        currency=item.currency,
        applicant_id=item.creator_id,
        source_no=item.no,
        allow_pending=True,
    )
    write_audit(
        db,
        user=None,
        action="AUTO_REVENUE_FROM_ACCEPTANCE",
        target_type="REVENUE",
        target_id=item.id,
        company_id=project.company_id,
        after={"acceptance_id": acceptance_id, "amount": str(amount)},
    )
    return item
