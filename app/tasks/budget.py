from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.celery_app import celery_app
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.finance import Budget, CostRecord
from app.models.project import Project
from app.services.cost.budget import check_budget_alert
from app.services.iam.notification import notify_with_email
from app.utils.datetime import today

logger = get_logger("eoms.tasks.budget")


@celery_app.task(name="eoms.budget.scan_alerts")
def scan_alerts(year: int | None = None) -> dict[str, int]:
    """定期扫描全部进行中项目的预算执行率，触发预警通知（同日同科目去重）。"""
    year = year or today().year
    triggered = 0
    with session_scope() as db:
        budgets = (
            db.execute(
                select(Budget)
                .where(Budget.year == year)
                .order_by(Budget.project_id, Budget.account_code)
            )
            .scalars()
            .all()
        )
        seen: set[tuple[int, str]] = set()
        for budget in budgets:
            key = (int(budget.project_id), str(budget.account_code))
            if key in seen:
                continue
            seen.add(key)
            if check_budget_alert(db, budget.project_id, budget.account_code, year):
                triggered += 1

        # 无预算但已发生成本的项目：提示补录预算
        projects = (
            db.execute(
                select(Project).where(Project.status.in_(["ACTIVE", "PENDING"]))
            )
            .scalars()
            .all()
        )
        for project in projects:
            if project.budget_amount and Decimal(str(project.budget_amount)) > 0:
                continue
            actual = Decimal(
                str(
                    db.execute(
                        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
                            CostRecord.project_id == project.id,
                            CostRecord.status == "ACTIVE",
                            CostRecord.period.like(f"{year}-%"),
                        )
                    ).scalar_one()
                    or 0
                )
            )
            if actual <= 0:
                continue
            notify_with_email(
                db,
                company_id=project.company_id,
                user_ids=[project.manager_id],
                title=f"项目预算缺失：{project.name}",
                content=f"项目「{project.name}」已发生成本 {actual:.2f} 元，但未设置年度预算，请及时补录。",
                type="ALERT",
                biz_type="BUDGET",
                biz_id=project.id,
                link=f"/projects/{project.id}?tab=budget",
                email=False,
            )
            triggered += 1
    logger.info("预算预警扫描完成：年=%s 触发=%s 阈值=%s", year, triggered, settings.budget_alert_threshold)
    return {"year": year, "triggered": triggered}
