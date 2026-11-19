from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.models.enums import PeriodStatus
from app.models.finance import CostRecord, Period
from app.models.iam import User
from app.services.iam.audit import write_audit
from app.utils.datetime import now, period_of


def ensure_period_open(db: Session, company_id: int, occur_date: date) -> str:
    period = period_of(occur_date)
    row = db.execute(
        select(Period).where(Period.company_id == company_id, Period.period == period)
    ).scalar_one_or_none()
    if row is not None and row.status == PeriodStatus.CLOSED.value:
        raise BusinessRuleError(f"期间 {period} 已关账，禁止写入成本数据")
    return period


def record_cost(
    db: Session,
    *,
    company_id: int,
    dept_id: int | None,
    project_id: int | None,
    biz_type: str,
    biz_id: int,
    account_code: str,
    amount: Decimal,
    occur_date: date,
    currency: str = "CNY",
    vendor_id: int | None = None,
    contract_id: int | None = None,
    applicant_id: int | None = None,
    source_no: str | None = None,
    cash_date: date | None = None,
) -> CostRecord:
    amount = Decimal(str(amount))
    if amount == 0:
        raise BusinessRuleError("入账金额不能为 0")
    period = ensure_period_open(db, company_id, occur_date)
    record_key = f"{biz_type}:{biz_id}:{account_code}"
    existing = db.execute(
        select(CostRecord).where(CostRecord.record_key == record_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    record = CostRecord(
        record_key=record_key,
        company_id=company_id,
        dept_id=dept_id,
        project_id=project_id,
        biz_type=biz_type,
        biz_id=biz_id,
        account_code=account_code,
        amount=amount,
        currency=currency,
        occur_date=occur_date,
        period=period,
        vendor_id=vendor_id,
        contract_id=contract_id,
        applicant_id=applicant_id,
        source_no=source_no,
        status="ACTIVE",
        cash_date=cash_date,
    )
    db.add(record)
    db.flush()
    return record


def reverse_cost(db: Session, record_id: int, user: User, reason: str) -> CostRecord:
    original = db.get(CostRecord, record_id)
    if original is None or original.company_id != user.company_id:
        raise NotFoundError("成本记录不存在")
    if original.is_reversal or original.status != "ACTIVE":
        raise BusinessRuleError("该记录已冲销或不可冲销")
    if not reason or len(reason.strip()) < 2:
        raise BusinessRuleError("请填写冲销原因")
    today = now().date()
    period = ensure_period_open(db, original.company_id, today)
    reversal = CostRecord(
        record_key=f"REV:{original.id}",
        company_id=original.company_id,
        dept_id=original.dept_id,
        project_id=original.project_id,
        biz_type=original.biz_type,
        biz_id=original.biz_id,
        account_code=original.account_code,
        amount=-original.amount,
        currency=original.currency,
        occur_date=today,
        period=period,
        vendor_id=original.vendor_id,
        contract_id=original.contract_id,
        applicant_id=original.applicant_id,
        source_no=original.source_no,
        status="ACTIVE",
        cash_date=None,
        is_reversal=True,
        reversal_of_id=original.id,
    )
    original.status = "REVERSED"
    db.add(reversal)
    db.flush()
    write_audit(
        db,
        user=user,
        action="REVERSE_COST",
        target_type="COST_RECORD",
        target_id=original.id,
        before={"amount": str(original.amount)},
        after={"reversal_id": reversal.id, "reason": reason},
    )
    return reversal


def update_cash_date(db: Session, *, biz_type: str, biz_id: int, cash_date: date) -> int:
    rows = db.execute(
        select(CostRecord).where(
            CostRecord.biz_type == biz_type,
            CostRecord.biz_id == biz_id,
            CostRecord.is_reversal.is_(False),
        )
    ).scalars()
    count = 0
    for row in rows:
        row.cash_date = cash_date
        count += 1
    db.flush()
    return count
