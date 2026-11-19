from __future__ import annotations

from sqlalchemy import func, select

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.finance import CostRecord
from app.models.project import Project
from app.services.iam.notification import notify_with_email
from app.utils.datetime import today

logger = get_logger("eoms.tasks.project")


@celery_app.task(name="eoms.project.health_check")
def health_check(delay_days: int = 1) -> dict[str, int]:
    """项目健康巡检：进度滞后或成本超预算时提醒项目经理与总监。"""
    alerted = 0
    with session_scope() as db:
        projects = (
            db.execute(select(Project).where(Project.status == "ACTIVE"))
            .scalars()
            .all()
        )
        for project in projects:
            reasons: list[str] = []
            if project.plan_end and project.plan_end < today():
                delay = (today() - project.plan_end).days
                if delay >= delay_days and (project.progress or 0) < 100:
                    reasons.append(f"计划完成日 {project.plan_end} 已逾期 {delay} 天，当前进度 {project.progress}%")
            budget = float(project.budget_amount or 0)
            if budget > 0:
                actual = float(
                    db.execute(
                        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
                            CostRecord.project_id == project.id,
                            CostRecord.status == "ACTIVE",
                        )
                    ).scalar_one()
                    or 0
                )
                if actual > budget:
                    reasons.append(f"实际成本 {actual:.2f} 元已超过预算 {budget:.2f} 元")
            if not reasons:
                continue
            notify_with_email(
                db,
                company_id=project.company_id,
                user_ids=[uid for uid in (project.manager_id, project.creator_id) if uid],
                title=f"项目健康预警：{project.name}",
                content="；".join(reasons),
                type="ALERT",
                biz_type="PROJECT",
                biz_id=project.id,
                link=f"/projects/{project.id}",
                email=False,
            )
            alerted += 1
    logger.info("项目健康巡检完成：提醒=%s", alerted)
    return {"alerted": alerted}
