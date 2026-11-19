from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.approval import Expense
from app.models.enums import ExpenseStatus, PaymentStatus, VendorType
from app.models.finance import Payment
from app.models.iam import User
from app.models.project import Project
from app.models.vendor import Contract, Vendor, VendorProject
from app.services.approval.expense import get_expense, mark_paid
from app.services.common import company_code, users_by_role
from app.services.cost.budget import check_budget_alert
from app.services.cost.ledger import ensure_period_open, record_cost
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.services.project.project import get_project
from app.utils.datetime import now, to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import next_no

VENDOR_ACCOUNT = {
    VendorType.SUBCONTRACT.value: "5401",
    VendorType.MATERIAL.value: "5402",
    VendorType.SERVICE.value: "5403",
    VendorType.LEASE.value: "5404",
}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Payment)
    condition = scope_condition(ctx, Payment)
    return stmt.where(condition) if condition is not None else stmt


def list_payments(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    project_id: int | None = None,
    vendor_id: int | None = None,
    status: str | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if project_id:
        stmt = stmt.where(Payment.project_id == project_id)
    if vendor_id:
        stmt = stmt.where(Payment.vendor_id == vendor_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    stmt = stmt.order_by(Payment.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_payment(db: Session, ctx: ScopeContext, payment_id: int) -> Payment:
    item = db.execute(_base_query(ctx).where(Payment.id == payment_id)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("付款单不存在或无权访问")
    return item


def create_payment(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Payment:
    project = get_project(db, ctx, int(payload.get("project_id") or 0))
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增付款")
    amount = to_decimal(payload.get("amount"), field_name="付款金额")
    if amount <= 0:
        raise BusinessRuleError("付款金额必须大于 0")
    expense_id = payload.get("expense_id")
    vendor_id = payload.get("vendor_id")
    contract_id = payload.get("contract_id")
    vendor: Vendor | None = None
    contract: Contract | None = None
    account_code = str(payload.get("account_code") or "")

    if expense_id:
        expense = get_expense(db, ctx, int(expense_id))
        if expense.status not in {ExpenseStatus.APPROVED.value, ExpenseStatus.VERIFIED.value}:
            raise BusinessRuleError("报销单未审批通过或已付款")
        if Decimal(str(expense.amount_total)) != amount:
            raise BusinessRuleError("付款金额必须等于报销单金额")
        exists = db.execute(
            select(Payment).where(
                Payment.expense_id == expense.id,
                Payment.status.in_([PaymentStatus.PENDING.value, PaymentStatus.PAID.value]),
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise BusinessRuleError("该报销单已存在付款单")
        if expense.project_id:
            project = db.get(Project, expense.project_id) or project
        account_code = ""

    if vendor_id:
        vendor = db.get(Vendor, int(vendor_id))
        if vendor is None or vendor.company_id != user.company_id:
            raise BusinessRuleError("供应商不存在")
        if vendor.status == "BLACKLIST":
            raise BusinessRuleError("黑名单供应商禁止付款")
        account_code = account_code or VENDOR_ACCOUNT.get(vendor.type, "5401")
    if contract_id:
        contract = db.get(Contract, int(contract_id))
        if contract is None or contract.company_id != user.company_id:
            raise BusinessRuleError("合同不存在")
        if vendor and contract.vendor_id != vendor.id:
            raise BusinessRuleError("合同与供应商不匹配")
        if contract.project_id and contract.project_id != project.id:
            raise BusinessRuleError("合同不属于该项目")
        if contract.status == "TERMINATED":
            raise BusinessRuleError("合同已终止，不能付款")
        if not vendor:
            vendor = db.get(Vendor, contract.vendor_id)
    if not vendor and not expense_id:
        raise BusinessRuleError("请选择供应商或关联报销单")
    if vendor and not account_code:
        account_code = VENDOR_ACCOUNT.get(vendor.type, "5401")

    payment = Payment(
        company_id=user.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=user.id,
        no=next_no(db, "PAY", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        vendor_id=vendor.id if vendor else None,
        contract_id=contract.id if contract else None,
        expense_id=int(expense_id) if expense_id else None,
        applicant_id=user.id,
        amount=amount,
        currency=str(payload.get("currency") or "CNY")[:8],
        pay_date=to_date(payload.get("pay_date")),
        method=str(payload.get("method") or "BANK"),
        status=PaymentStatus.PENDING.value,
        account_code=account_code[:32],
        remark=(payload.get("remark") or "")[:1000],
        installments_json=payload.get("installments") or [],
    )
    db.add(payment)
    db.flush()
    write_audit(
        db, user=user, action="CREATE_PAYMENT", target_type="PAYMENT", target_id=payment.id, after=snapshot(payment)
    )
    return payment


def pay_payment(db: Session, user: User, ctx: ScopeContext, payment_id: int, pay_date=None) -> Payment:
    payment = get_payment(db, ctx, payment_id)
    if payment.status != PaymentStatus.PENDING.value:
        raise BusinessRuleError("仅待付款状态可执行付款")
    actual_date = to_date(pay_date) or today()
    ensure_period_open(db, payment.company_id, actual_date)
    payment.status = PaymentStatus.PAID.value
    payment.pay_date = actual_date
    payment.version = int(payment.version or 1) + 1
    db.flush()

    if payment.expense_id:
        expense = db.get(Expense, payment.expense_id)
        if expense is None:
            raise BusinessRuleError("关联报销单不存在")
        mark_paid(db, expense, actual_date, user)
    else:
        record_cost(
            db,
            company_id=payment.company_id,
            dept_id=payment.dept_id,
            project_id=payment.project_id,
            biz_type="PAYMENT",
            biz_id=payment.id,
            account_code=payment.account_code or "5401",
            amount=Decimal(str(payment.amount)),
            occur_date=actual_date,
            currency=payment.currency,
            vendor_id=payment.vendor_id,
            contract_id=payment.contract_id,
            applicant_id=payment.applicant_id,
            source_no=payment.no,
            cash_date=actual_date,
        )
        check_budget_alert(db, payment.project_id, payment.account_code or "5401", actual_date.year)
        if payment.contract_id:
            _sync_vendor_project(db, payment)
            _check_contract_overrun(db, payment)
    write_audit(db, user=user, action="PAY_PAYMENT", target_type="PAYMENT", target_id=payment.id)
    notify_with_email(
        db,
        company_id=payment.company_id,
        user_ids=[payment.applicant_id],
        title=f"付款已完成：{payment.no}",
        content=f"付款单 {payment.no} 已完成付款，金额 {payment.amount} 元。",
        type="SYSTEM",
        biz_type="PAYMENT",
        biz_id=payment.id,
        link="/finance/payments",
        email=False,
    )
    return payment


def _sync_vendor_project(db: Session, payment: Payment) -> None:
    if not payment.vendor_id or not payment.project_id:
        return
    row = db.execute(
        select(VendorProject).where(
            VendorProject.vendor_id == payment.vendor_id,
            VendorProject.project_id == payment.project_id,
            VendorProject.contract_id == payment.contract_id,
        )
    ).scalar_one_or_none()
    if row is None:
        contract = db.get(Contract, payment.contract_id) if payment.contract_id else None
        row = VendorProject(
            company_id=payment.company_id,
            vendor_id=payment.vendor_id,
            project_id=payment.project_id,
            contract_id=payment.contract_id,
            role="供应商",
            contract_amount=Decimal(str(contract.amount)) if contract else Decimal("0.00"),
            paid_amount=Decimal("0.00"),
            settled_amount=Decimal("0.00"),
            score=Decimal("0.00"),
        )
        db.add(row)
        db.flush()
    row.paid_amount = Decimal(str(row.paid_amount)) + Decimal(str(payment.amount))
    db.flush()


def _check_contract_overrun(db: Session, payment: Payment) -> None:
    if not payment.contract_id:
        return
    contract = db.get(Contract, payment.contract_id)
    if contract is None:
        return
    paid = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.contract_id == contract.id, Payment.status == "PAID"
        )
    ).scalar_one()
    if Decimal(str(paid)) > Decimal(str(contract.amount)):
        recipients = {contract.creator_id, payment.applicant_id}
        recipients.update(user.id for user in users_by_role(db, contract.company_id, "FINANCE"))
        notify_with_email(
            db,
            company_id=contract.company_id,
            user_ids=sorted(uid for uid in recipients if uid),
            title=f"付款超合同金额预警：{contract.no}",
            content=(
                f"合同 {contract.no} 金额 {contract.amount} 元，累计付款 {paid} 元，已超出合同金额，请核实。"
            ),
            type="ALERT",
            biz_type="CONTRACT",
            biz_id=contract.id,
            link="/contracts",
            email=True,
        )


def cancel_payment(db: Session, user: User, ctx: ScopeContext, payment_id: int) -> Payment:
    payment = get_payment(db, ctx, payment_id)
    if payment.status != PaymentStatus.PENDING.value:
        raise BusinessRuleError("仅待付款状态可取消")
    payment.status = PaymentStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_PAYMENT", target_type="PAYMENT", target_id=payment.id)
    return payment
