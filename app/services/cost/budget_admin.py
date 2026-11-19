"""预算维护（按项目 + 科目 + 年度）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.scope import ScopeContext, assert_project_access
from app.models.finance import Account, Budget
from app.models.iam import User
from app.models.project import Project
from app.services.cost.budget import budget_status
from app.services.iam.audit import snapshot, write_audit
from app.utils.money import to_decimal


def list_budgets(db: Session, ctx: ScopeContext, project_id: int, year: int | None = None) -> dict:
    project = db.get(Project, project_id)
    if project is None or project.company_id != ctx.company_id:
        raise NotFoundError("项目不存在")
    assert_project_access(db, ctx, project_id)
    stmt = select(Budget).where(Budget.project_id == project_id)
    if year:
        stmt = stmt.where(Budget.year == year)
    rows = list(db.execute(stmt.order_by(Budget.year.desc(), Budget.account_code)).scalars().all())
    return {"items": rows, "status": budget_status(db, project_id, year) if year else None}


def save_budget(db: Session, user: User, ctx: ScopeContext, payload: dict) -> Budget:
    project_id = int(payload.get("project_id") or 0)
    project = db.get(Project, project_id)
    if project is None or project.company_id != ctx.company_id:
        raise NotFoundError("项目不存在")
    assert_project_access(db, ctx, project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能维护预算")
    account_code = str(payload.get("account_code") or "").strip()
    account = db.execute(
        select(Account).where(Account.company_id == ctx.company_id, Account.code == account_code)
    ).scalar_one_or_none()
    if account is None:
        raise BusinessRuleError("费用科目不存在")
    year = int(payload.get("year") or 0)
    amount = to_decimal(payload.get("amount"), field_name="预算金额")
    if amount < 0:
        raise BusinessRuleError("预算金额不能为负数")
    row = db.execute(
        select(Budget).where(
            Budget.company_id == ctx.company_id,
            Budget.project_id == project_id,
            Budget.account_code == account_code,
            Budget.year == year,
        )
    ).scalar_one_or_none()
    if row is not None:
        expected = payload.get("version")
        if expected is not None and int(expected) != row.version:
            raise ConflictError("预算已被修改，请刷新后重试")
        before = snapshot(row)
        row.amount = amount
        row.remark = (payload.get("remark") or "")[:255] or None
        row.version = int(row.version or 1) + 1
        db.flush()
        write_audit(
            db,
            user=user,
            action="UPDATE_BUDGET",
            target_type="BUDGET",
            target_id=row.id,
            before=before,
            after=snapshot(row),
        )
        return row
    row = Budget(
        company_id=ctx.company_id,
        project_id=project_id,
        account_code=account_code,
        year=year,
        amount=amount,
        remark=(payload.get("remark") or "")[:255] or None,
        creator_id=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, user=user, action="CREATE_BUDGET", target_type="BUDGET", target_id=row.id, after=snapshot(row))
    return row


def delete_budget(db: Session, user: User, ctx: ScopeContext, budget_id: int) -> None:
    row = db.get(Budget, budget_id)
    if row is None or row.company_id != ctx.company_id:
        raise NotFoundError("预算不存在")
    assert_project_access(db, ctx, row.project_id)
    from app.services.cost.budget import actual_amount

    if actual_amount(db, row.project_id, row.account_code, row.year) > 0:
        raise BusinessRuleError("该科目已发生实际成本，不能删除预算")
    db.delete(row)
    db.flush()
    write_audit(db, user=user, action="DELETE_BUDGET", target_type="BUDGET", target_id=budget_id)


def list_accounts(db: Session, ctx: ScopeContext) -> list[Account]:
    return list(
        db.execute(
            select(Account)
            .where(Account.company_id == ctx.company_id, Account.status == "ACTIVE")
            .order_by(Account.code)
        )
        .scalars()
        .all()
    )
