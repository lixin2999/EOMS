from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.models.finance import Budget, CostRecord
from app.models.project import Project
from app.services.common import users_by_role
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now, today

ZERO = Decimal("0.00")


def budget_amount(db: Session, project_id: int, account_code: str, year: int) -> Decimal:
    value = db.execute(
        select(Budget.amount).where(
            Budget.project_id == project_id,
            Budget.account_code == account_code,
            Budget.year == year,
        )
    ).scalar_one_or_none()
    return Decimal(str(value or 0))


def actual_amount(db: Session, project_id: int, account_code: str, year: int | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
        CostRecord.project_id == project_id,
        CostRecord.account_code == account_code,
        CostRecord.status == "ACTIVE",
    )
    if year:
        stmt = stmt.where(CostRecord.period.like(f"{year}-%"))
    value = db.execute(stmt).scalar_one()
    return Decimal(str(value or 0))


def budget_overview(db: Session, project_id: int, year: int) -> list[dict]:
    rows = list(
        db.execute(
            select(Budget).where(Budget.project_id == project_id, Budget.year == year).order_by(Budget.account_code)
        )
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        actual = actual_amount(db, project_id, row.account_code, year)
        budget = Decimal(str(row.amount))
        rate = float(actual / budget) if budget > 0 else 0.0
        result.append(
            {
                "account_code": row.account_code,
                "budget": budget,
                "actual": actual,
                "rate": round(rate, 4),
                "alert": budget > 0 and actual >= budget * Decimal(str(settings.budget_alert_threshold)),
            }
        )
    return result


def check_budget_alert(db: Session, project_id: int | None, account_code: str, year: int) -> bool:
    if not project_id:
        return False
    budget = budget_amount(db, project_id, account_code, year)
    if budget <= 0:
        return False
    actual = actual_amount(db, project_id, account_code, year)
    threshold = budget * Decimal(str(settings.budget_alert_threshold))
    if actual < threshold:
        return False
    cache_key = f"budget_alert:{project_id}:{account_code}:{year}"
    if cache.get(cache_key):
        return False
    cache.set(cache_key, "1", 86400)

    project = db.get(Project, project_id)
    if project is None:
        return False
    recipients = {project.manager_id}
    recipients.update(user.id for user in users_by_role(db, project.company_id, "FINANCE"))
    recipients.update(user.id for user in users_by_role(db, project.company_id, "DIRECTOR"))
    rate = float(actual / budget) if budget else 0.0
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=sorted(recipients),
        title=f"预算预警：{project.name} / 科目 {account_code}",
        content=(
            f"项目「{project.name}」科目 {account_code} 已发生 {actual:.2f} 元，"
            f"预算 {budget:.2f} 元，使用率 {rate:.1%}，已达预警阈值。"
        ),
        type="ALERT",
        biz_type="BUDGET",
        biz_id=project.id,
        link=f"/projects/{project.id}?tab=budget",
        email=True,
    )
    return True


def budget_status(db: Session, project_id: int, year: int | None = None) -> dict:
    year = year or today().year
    rows = budget_overview(db, project_id, year)
    total_budget = sum((item["budget"] for item in rows), ZERO)
    total_actual = sum((item["actual"] for item in rows), ZERO)
    return {
        "year": year,
        "total_budget": total_budget,
        "total_actual": total_actual,
        "rate": round(float(total_actual / total_budget), 4) if total_budget else 0.0,
        "rows": rows,
        "generated_at": now().isoformat(),
    }
