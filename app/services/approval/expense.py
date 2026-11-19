from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.approval import Expense, ExpenseItem
from app.models.enums import ExpenseStatus, ExpenseType
from app.models.iam import User
from app.models.project import Project
from app.models.workflow import WorkflowInstance
from app.services.common import claim_version, company_code, ensure_choice, ensure_files, users_by_role
from app.services.cost.accounts import CATEGORY_ACCOUNT, category_amounts
from app.services.cost.budget import check_budget_alert
from app.services.cost.ledger import ensure_period_open, record_cost, update_cash_date
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now, period_of, to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import next_no
from app.workflow import engine

EXPENSE_TYPES = {item.value for item in ExpenseType}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Expense)
    condition = scope_condition(ctx, Expense)
    return stmt.where(condition) if condition is not None else stmt


def list_expenses(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str | None = None,
    project_id: int | None = None,
    applicant_id: int | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if status:
        stmt = stmt.where(Expense.status == status)
    if project_id:
        stmt = stmt.where(Expense.project_id == project_id)
    if applicant_id:
        stmt = stmt.where(Expense.applicant_id == applicant_id)
    if keyword:
        stmt = stmt.where(or_(Expense.no.like(f"%{keyword}%"), Expense.payee.like(f"%{keyword}%")))
    if date_from:
        stmt = stmt.where(Expense.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Expense.created_at <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(Expense.id.desc())
    count = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": count, "page": params.page, "page_size": params.page_size}


def get_expense(db: Session, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = db.execute(_base_query(ctx).where(Expense.id == expense_id)).scalar_one_or_none()
    if expense is None:
        raise NotFoundError("报销单不存在或无权访问")
    return expense


def _validate_project(db: Session, ctx: ScopeContext, project_id: int | None) -> Project:
    if not project_id:
        raise BusinessRuleError("请选择归属项目")
    project = db.get(Project, project_id)
    if project is None or project.company_id != ctx.company_id:
        raise BusinessRuleError("项目不存在")
    if project.status in {"CLOSED", "CANCELED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增费用")
    from app.core.scope import assert_project_access

    assert_project_access(db, ctx, project_id)
    return project


def _normalize_items(raw_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal]:
    if not raw_items:
        raise BusinessRuleError("请至少填写一条费用明细")
    if len(raw_items) > 100:
        raise BusinessRuleError("费用明细不得超过 100 条")
    normalized: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for row in raw_items:
        category = ensure_choice(str(row.get("category") or ""), set(CATEGORY_ACCOUNT), "费用类别")
        amount = to_decimal(row.get("amount"), field_name="明细金额")
        if amount <= 0:
            raise BusinessRuleError("明细金额必须大于 0")
        if amount > Decimal("10000000"):
            raise BusinessRuleError("单条明细金额超出合理范围")
        occur = to_date(row.get("occur_date")) or today()
        description = (row.get("description") or "")[:500]
        file_id = row.get("file_id")
        normalized.append(
            {
                "category": category,
                "amount": str(amount),
                "occur_date": occur.isoformat(),
                "description": description,
                "file_id": int(file_id) if file_id else None,
            }
        )
        total += amount
    return normalized, total


def _replace_items(db: Session, expense: Expense, items: list[dict[str, Any]]) -> None:
    db.execute(delete(ExpenseItem).where(ExpenseItem.expense_id == expense.id))
    for row in items:
        db.add(
            ExpenseItem(
                expense_id=expense.id,
                category=row["category"],
                amount=Decimal(row["amount"]),
                occur_date=to_date(row["occur_date"]),
                description=row["description"],
                file_id=row["file_id"],
            )
        )
    db.flush()


def create_expense(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Expense:
    expense_type = ensure_choice(str(payload.get("type") or "OTHER"), EXPENSE_TYPES, "报销类型")
    project = _validate_project(db, ctx, payload.get("project_id"))
    items, total = _normalize_items(payload.get("items") or [])
    invoices = ensure_files(db, payload.get("invoices_file_ids") or [], user.company_id)
    if total <= 0:
        raise BusinessRuleError("报销金额必须大于 0")
    expense = Expense(
        company_id=user.company_id,
        dept_id=user.dept_id,
        project_id=project.id,
        creator_id=user.id,
        applicant_id=user.id,
        no=next_no(db, "EXP", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        type=expense_type,
        amount_total=total,
        currency=str(payload.get("currency") or "CNY")[:8],
        items_json=items,
        invoices_file_ids=invoices,
        payee=(payload.get("payee") or user.real_name)[:128],
        remark=(payload.get("remark") or "")[:1000],
        status=ExpenseStatus.DRAFT.value,
    )
    db.add(expense)
    db.flush()
    _replace_items(db, expense, items)
    write_audit(
        db,
        user=user,
        action="CREATE_EXPENSE",
        target_type="EXPENSE",
        target_id=expense.id,
        after=snapshot(expense),
    )
    return expense


def update_expense(
    db: Session, user: User, ctx: ScopeContext, expense_id: int, payload: dict[str, Any]
) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if expense.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能修改本人报销单")
    if expense.status not in {ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许修改")
    expected_version = payload.get("version")
    if expected_version is not None and int(expected_version) != expense.version:
        raise ConflictError("报销单已被修改，请刷新后重试")
    before = snapshot(expense)
    if payload.get("project_id") is not None:
        _validate_project(db, ctx, payload.get("project_id"))
        expense.project_id = int(payload["project_id"])
    if payload.get("type") is not None:
        expense.type = ensure_choice(str(payload["type"]), EXPENSE_TYPES, "报销类型")
    if payload.get("items") is not None:
        items, total = _normalize_items(payload["items"])
        expense.items_json = items
        expense.amount_total = total
        _replace_items(db, expense, items)
    if payload.get("invoices_file_ids") is not None:
        expense.invoices_file_ids = ensure_files(db, payload["invoices_file_ids"], user.company_id)
    if payload.get("payee") is not None:
        expense.payee = str(payload["payee"])[:128]
    if payload.get("remark") is not None:
        expense.remark = str(payload["remark"])[:1000]
    expense.version = int(expense.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_EXPENSE",
        target_type="EXPENSE",
        target_id=expense.id,
        before=before,
        after=snapshot(expense),
    )
    return expense


def submit_expense(db: Session, user: User, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if expense.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能提交本人报销单")
    if expense.status not in {ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许提交")
    if not expense.items_json:
        raise BusinessRuleError("请至少填写一条费用明细")
    if not expense.invoices_file_ids:
        raise BusinessRuleError("请上传发票附件后再提交")
    if not expense.project_id:
        raise BusinessRuleError("请选择归属项目")
    project = db.get(Project, expense.project_id)
    if project is None or project.company_id != user.company_id:
        raise BusinessRuleError("项目不存在")
    if project.status in {"CLOSED", "CANCELED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能提交报销")
    ensure_files(db, expense.invoices_file_ids, user.company_id)
    for item in expense.items_json:
        ensure_period_open(db, user.company_id, to_date(item.get("occur_date")) or today())

    claim_version(
        db,
        Expense,
        expense,
        allowed_status={ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value},
    )
    expense.status = ExpenseStatus.RUNNING.value
    expense.submitted_at = now()
    expense.workflow_version = int(expense.workflow_version or 0) + 1
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=expense.dept_id,
        project_id=expense.project_id,
        initiator=user,
        def_code="EXPENSE",
        biz_type="EXPENSE",
        biz_id=expense.id,
        title=f"报销单 {expense.no}（{expense.amount_total} 元）",
        context={
            "amount": str(expense.amount_total),
            "type": expense.type,
            "category": (expense.items_json[0] or {}).get("category") if expense.items_json else "",
            "no": expense.no,
            "project_id": expense.project_id,
        },
        version=expense.workflow_version,
    )
    expense.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="SUBMIT_EXPENSE",
        target_type="EXPENSE",
        target_id=expense.id,
        after={"instance_id": instance.id, "amount": str(expense.amount_total)},
    )
    return expense


def cancel_expense(db: Session, user: User, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if expense.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能取消本人报销单")
    if expense.status not in {ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许取消")
    expense.status = ExpenseStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_EXPENSE", target_type="EXPENSE", target_id=expense.id)
    return expense


def withdraw_expense(db: Session, user: User, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if not expense.instance_id:
        raise BusinessRuleError("该报销单尚未提交审批")
    engine.act(db, user=user, instance_id=expense.instance_id, action="WITHDRAW")
    db.refresh(expense)
    return expense


def finance_verify(db: Session, user: User, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if expense.status != ExpenseStatus.APPROVED.value:
        raise BusinessRuleError("仅审批通过的报销单可进行财务复核")
    expense.status = ExpenseStatus.VERIFIED.value
    expense.verified_at = now()
    expense.version = int(expense.version or 1) + 1
    db.flush()
    write_audit(db, user=user, action="VERIFY_EXPENSE", target_type="EXPENSE", target_id=expense.id)
    return expense


def archive_expense(db: Session, user: User, ctx: ScopeContext, expense_id: int) -> Expense:
    expense = get_expense(db, ctx, expense_id)
    if expense.status != ExpenseStatus.PAID.value:
        raise BusinessRuleError("仅已付款的报销单可归档")
    expense.status = ExpenseStatus.ARCHIVED.value
    expense.archived_at = now()
    db.flush()
    write_audit(db, user=user, action="ARCHIVE_EXPENSE", target_type="EXPENSE", target_id=expense.id)
    return expense


def mark_paid(db: Session, expense: Expense, pay_date: date, operator: User) -> None:
    if expense.status == ExpenseStatus.PAID.value:
        return
    if expense.status not in {ExpenseStatus.APPROVED.value, ExpenseStatus.VERIFIED.value}:
        raise BusinessRuleError("报销单尚未审批通过，不能付款")
    expense.status = ExpenseStatus.PAID.value
    expense.paid_at = now()
    update_cash_date(db, biz_type="EXPENSE", biz_id=expense.id, cash_date=pay_date)
    db.flush()
    write_audit(db, user=operator, action="PAY_EXPENSE", target_type="EXPENSE", target_id=expense.id)
    notify_with_email(
        db,
        company_id=expense.company_id,
        user_ids=[expense.applicant_id],
        title=f"报销已付款：{expense.no}",
        content=f"报销单 {expense.no} 已完成付款，金额 {expense.amount_total} 元。",
        type="APPROVAL",
        biz_type="EXPENSE",
        biz_id=expense.id,
        link=f"/approvals/expenses/{expense.id}",
        email=False,
    )


# ---------------------------------------------------------------- 审批回调
def on_approved(db: Session, instance: WorkflowInstance) -> None:
    expense = db.get(Expense, instance.biz_id)
    if expense is None:
        raise BusinessRuleError("报销单不存在")
    if expense.status in {ExpenseStatus.PAID.value, ExpenseStatus.ARCHIVED.value, ExpenseStatus.VERIFIED.value}:
        return
    expense.status = ExpenseStatus.APPROVED.value
    db.flush()
    occur = max(
        (to_date(item.get("occur_date")) or today() for item in (expense.items_json or [])),
        default=today(),
    )
    for account_code, amount in category_amounts(expense.items_json or []).items():
        # 期间已关账时把入账请求暂存，审批动作照常完成，开账后由任务补记。
        record = record_cost(
            db,
            company_id=expense.company_id,
            dept_id=expense.dept_id,
            project_id=expense.project_id,
            biz_type="EXPENSE",
            biz_id=expense.id,
            account_code=account_code,
            amount=amount,
            occur_date=occur,
            currency=expense.currency,
            applicant_id=expense.applicant_id,
            source_no=expense.no,
            allow_pending=True,
        )
        if record is not None:
            check_budget_alert(db, expense.project_id, account_code, occur.year)
    finance_ids = [item.id for item in users_by_role(db, expense.company_id, "FINANCE")]
    notify_with_email(
        db,
        company_id=expense.company_id,
        user_ids=finance_ids,
        title=f"待付款：报销单 {expense.no}",
        content=f"报销单 {expense.no} 已审批通过，金额 {expense.amount_total} 元，请安排付款。",
        type="APPROVAL",
        biz_type="EXPENSE",
        biz_id=expense.id,
        link=f"/approvals/expenses/{expense.id}",
        email=True,
    )
    write_audit(
        db,
        user=None,
        action="EXPENSE_APPROVED",
        target_type="EXPENSE",
        target_id=expense.id,
        company_id=expense.company_id,
        after={"cost_period": period_of(occur)},
    )


def on_rejected(db: Session, instance: WorkflowInstance) -> None:
    expense = db.get(Expense, instance.biz_id)
    if expense and expense.status == ExpenseStatus.RUNNING.value:
        expense.status = ExpenseStatus.REJECTED.value
        db.flush()


def on_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    expense = db.get(Expense, instance.biz_id)
    if expense and expense.status == ExpenseStatus.RUNNING.value:
        expense.status = ExpenseStatus.DRAFT.value
        db.flush()
