from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.enums import ReceiptStatus
from app.models.finance import CostRecord, Receipt
from app.models.iam import User
from app.models.platform import Customer
from app.services.common import company_code
from app.services.cost.ledger import record_cost, reverse_cost
from app.services.iam.audit import snapshot, write_audit
from app.services.project.project import get_project
from app.utils.datetime import now, to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import next_no

RECEIPT_ACCOUNT = "1002"


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Receipt)
    condition = scope_condition(ctx, Receipt)
    return stmt.where(condition) if condition is not None else stmt


def list_receipts(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    project_id: int | None = None,
    date_from=None,
    date_to=None,
) -> dict:
    stmt = _base_query(ctx)
    if project_id:
        stmt = stmt.where(Receipt.project_id == project_id)
    if date_from:
        stmt = stmt.where(Receipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(Receipt.receipt_date <= date_to)
    stmt = stmt.order_by(Receipt.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_receipt(db: Session, ctx: ScopeContext, receipt_id: int) -> Receipt:
    item = db.execute(_base_query(ctx).where(Receipt.id == receipt_id)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("收款单不存在或无权访问")
    return item


def create_receipt(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Receipt:
    project = get_project(db, ctx, int(payload.get("project_id") or 0))
    amount = to_decimal(payload.get("amount"), field_name="收款金额")
    if amount <= 0:
        raise BusinessRuleError("收款金额必须大于 0")
    receipt_date = to_date(payload.get("receipt_date")) or today()
    customer_id = payload.get("customer_id") or project.customer_id
    if customer_id:
        customer = db.get(Customer, int(customer_id))
        if customer is None or customer.company_id != user.company_id:
            raise BusinessRuleError("客户不存在")
    item = Receipt(
        company_id=user.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=user.id,
        no=next_no(db, "RCT", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        customer_id=int(customer_id) if customer_id else None,
        contract_id=payload.get("contract_id"),
        amount=amount,
        currency=str(payload.get("currency") or "CNY")[:8],
        receipt_date=receipt_date,
        method=str(payload.get("method") or "BANK"),
        status=ReceiptStatus.REGISTERED.value,
        remark=(payload.get("remark") or "")[:1000],
    )
    db.add(item)
    db.flush()
    record_cost(
        db,
        company_id=item.company_id,
        dept_id=item.dept_id,
        project_id=item.project_id,
        biz_type="RECEIPT",
        biz_id=item.id,
        account_code=RECEIPT_ACCOUNT,
        amount=amount,
        occur_date=receipt_date,
        currency=item.currency,
        contract_id=item.contract_id,
        applicant_id=user.id,
        source_no=item.no,
        cash_date=receipt_date,
    )
    write_audit(
        db, user=user, action="CREATE_RECEIPT", target_type="RECEIPT", target_id=item.id, after=snapshot(item)
    )
    return item


def cancel_receipt(db: Session, user: User, ctx: ScopeContext, receipt_id: int) -> Receipt:
    item = get_receipt(db, ctx, receipt_id)
    if item.status == ReceiptStatus.CANCELED.value:
        return item
    records = db.execute(
        select(CostRecord).where(
            CostRecord.biz_type == "RECEIPT",
            CostRecord.biz_id == item.id,
            CostRecord.status == "ACTIVE",
        )
    ).scalars()
    for record in records:
        reverse_cost(db, record.id, user, "收款作废冲销")
    item.status = ReceiptStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_RECEIPT", target_type="RECEIPT", target_id=item.id)
    return item
