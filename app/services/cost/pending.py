"""期间关账后的成本暂存与补记。

审批通过与成本归集解耦：期间已关账时，回调不再抛错回滚审批动作，而是把
入账请求写入 ``fin_pending_cost``；反关账或定时任务再把暂存记录补记到
``fin_cost_record``（依赖 ``record_key`` 保证幂等）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.finance import PendingCost
from app.services.common import users_by_role
from app.services.iam.audit import write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now

logger = get_logger("eoms.cost.pending")

PENDING = "PENDING"
POSTED = "POSTED"


def _normalize(**values: Any) -> dict[str, Any]:
    amount = Decimal(str(values["amount"]))
    return {
        "record_key": str(values["record_key"]),
        "company_id": int(values["company_id"]),
        "dept_id": values.get("dept_id"),
        "project_id": values.get("project_id"),
        "biz_type": str(values["biz_type"]),
        "biz_id": int(values["biz_id"]),
        "account_code": str(values["account_code"]),
        "amount": amount,
        "currency": str(values.get("currency") or "CNY"),
        "occur_date": values["occur_date"],
        "period": str(values["period"]),
        "vendor_id": values.get("vendor_id"),
        "contract_id": values.get("contract_id"),
        "applicant_id": values.get("applicant_id"),
        "source_no": values.get("source_no"),
        "cash_date": values.get("cash_date"),
        "reason": (values.get("reason") or "")[:255] or None,
    }


def queue_pending_cost(db: Session, **values: Any) -> PendingCost:
    """暂存一条待补记成本；按 ``record_key`` 幂等。"""
    data = _normalize(**values)
    existing = db.execute(
        select(PendingCost).where(PendingCost.record_key == data["record_key"])
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    item = PendingCost(**data, status=PENDING, retries=0)
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        existing = db.execute(
            select(PendingCost).where(PendingCost.record_key == data["record_key"])
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    write_audit(
        db,
        user=None,
        action="COST_PENDING",
        target_type="COST_PENDING",
        target_id=item.id,
        company_id=item.company_id,
        after={
            "biz_type": item.biz_type,
            "biz_id": item.biz_id,
            "account_code": item.account_code,
            "amount": str(item.amount),
            "period": item.period,
        },
    )
    finance_ids = [user.id for user in users_by_role(db, item.company_id, "FINANCE")]
    if finance_ids:
        notify_with_email(
            db,
            company_id=item.company_id,
            user_ids=finance_ids,
            title=f"期间已关账，成本已暂存：{item.period}",
            content=(
                f"单据 {item.source_no or item.biz_id} 的 {item.amount} 元成本因期间 "
                f"{item.period} 已关账而暂存，反关账后系统将自动补记。"
            ),
            type="ALERT",
            biz_type="COST_PENDING",
            biz_id=item.id,
            link="/finance/periods",
            email=False,
        )
    return item


def post_pending_costs(db: Session, *, company_id: int | None = None, limit: int = 200) -> dict[str, int]:
    """补记暂存成本；返回 ``{"posted": n, "pending": n, "failed": n}``。"""
    from app.services.cost.ledger import record_cost_checked

    stmt = select(PendingCost).where(PendingCost.status == PENDING)
    if company_id is not None:
        stmt = stmt.where(PendingCost.company_id == company_id)
    rows = list(db.execute(stmt.order_by(PendingCost.id).limit(limit)).scalars().all())
    posted = failed = 0
    for row in rows:
        try:
            with db.begin_nested():
                record, _ = record_cost_checked(
                    db,
                    company_id=row.company_id,
                    dept_id=row.dept_id,
                    project_id=row.project_id,
                    biz_type=row.biz_type,
                    biz_id=row.biz_id,
                    account_code=row.account_code,
                    amount=Decimal(str(row.amount)),
                    occur_date=row.occur_date,
                    currency=row.currency,
                    vendor_id=row.vendor_id,
                    contract_id=row.contract_id,
                    applicant_id=row.applicant_id,
                    source_no=row.source_no,
                    cash_date=row.cash_date,
                )
                row.status = POSTED
                row.cost_record_id = record.id if record is not None else None
                row.last_error = None
                db.flush()
            posted += 1
        except Exception as exc:  # noqa: BLE001 - 单条失败不阻断批次
            row.retries = int(row.retries or 0) + 1
            row.last_error = str(exc)[:2000]
            failed += 1
            logger.warning("待补记成本 %s 补记失败: %s", row.id, exc)
    remaining = int(
        db.execute(
            select(func.count(PendingCost.id)).where(
                PendingCost.status == PENDING,
                *([PendingCost.company_id == company_id] if company_id is not None else []),
            )
        ).scalar_one()
    )
    if posted:
        write_audit(
            db,
            user=None,
            action="POST_PENDING_COST",
            target_type="COST_PENDING",
            target_id=0,
            company_id=company_id,
            after={"posted": posted, "failed": failed, "limit": limit},
        )
    return {"posted": posted, "pending": remaining, "failed": failed, "total": len(rows)}


def pending_summary(db: Session, company_id: int, *, limit: int = 50) -> dict[str, Any]:
    """待补记清单与汇总，供财务核对。"""
    rows = list(
        db.execute(
            select(PendingCost)
            .where(PendingCost.company_id == company_id, PendingCost.status == PENDING)
            .order_by(PendingCost.period, PendingCost.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    total = db.execute(
        select(func.coalesce(func.sum(PendingCost.amount), 0)).where(
            PendingCost.company_id == company_id, PendingCost.status == PENDING
        )
    ).scalar_one()
    total_count = int(
        db.execute(
            select(func.count(PendingCost.id)).where(
                PendingCost.company_id == company_id, PendingCost.status == PENDING
            )
        ).scalar_one()
    )
    return {
        "count": len(rows),
        "total_count": total_count,
        "amount": Decimal(str(total)),
        "items": rows,
        "generated_at": now(),
    }


def pending_periods(db: Session, company_id: int) -> list[str]:
    """存在待补记记录的期间列表。"""
    return list(
        db.execute(
            select(PendingCost.period)
            .where(PendingCost.company_id == company_id, PendingCost.status == PENDING)
            .distinct()
            .order_by(PendingCost.period)
        ).scalars()
    )