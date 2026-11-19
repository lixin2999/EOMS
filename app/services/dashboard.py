"""首页驾驶舱：个人待办 + 经营概览 + 风险提醒。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.scope import ScopeContext
from app.models.approval import Expense, Leave
from app.models.platform import Notification
from app.models.project import Project
from app.models.vendor import VendorLicense
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.services.report import metrics
from app.services.vendor.contract import contract_risks
from app.services.vendor.vendor import vendor_risks
from app.utils.datetime import now, today


def personal_counts(db: Session, ctx: ScopeContext) -> dict:
    pending_tasks = int(
        db.execute(
            select(func.count(WorkflowTask.id)).where(
                WorkflowTask.assignee_id == ctx.user_id, WorkflowTask.status == "PENDING"
            )
        ).scalar_one()
    )
    my_running = int(
        db.execute(
            select(func.count(WorkflowInstance.id)).where(
                WorkflowInstance.initiator_id == ctx.user_id, WorkflowInstance.status == "RUNNING"
            )
        ).scalar_one()
    )
    unread = int(
        db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == ctx.user_id, Notification.read_at.is_(None)
            )
        ).scalar_one()
    )
    drafts = int(
        db.execute(
            select(func.count(Expense.id)).where(
                Expense.applicant_id == ctx.user_id, Expense.status.in_(["DRAFT", "REJECTED"])
            )
        ).scalar_one()
    )
    leaves = int(
        db.execute(
            select(func.count(Leave.id)).where(
                Leave.applicant_id == ctx.user_id, Leave.status.in_(["DRAFT", "REJECTED"])
            )
        ).scalar_one()
    )
    return {
        "pending_tasks": pending_tasks,
        "my_running": my_running,
        "unread_notifications": unread,
        "draft_expenses": drafts,
        "draft_leaves": leaves,
    }


def recent_tasks(db: Session, ctx: ScopeContext, limit: int = 8) -> list[dict]:
    rows = db.execute(
        select(WorkflowTask, WorkflowInstance)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
        .where(WorkflowTask.assignee_id == ctx.user_id, WorkflowTask.status == "PENDING")
        .order_by(WorkflowTask.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "task_id": task.id,
            "instance_id": instance.id,
            "biz_type": instance.biz_type,
            "biz_id": instance.biz_id,
            "title": instance.title,
            "node_name": task.node_name,
            "arrive_at": task.arrive_at,
            "due_at": task.due_at,
            "overdue": bool(task.due_at and task.due_at < now()),
            "initiator_id": instance.initiator_id,
        }
        for task, instance in rows
    ]


def recent_notifications(db: Session, ctx: ScopeContext, limit: int = 8) -> list[Notification]:
    return list(
        db.execute(
            select(Notification)
            .where(Notification.user_id == ctx.user_id)
            .order_by(Notification.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def project_health(db: Session, ctx: ScopeContext, limit: int = 8) -> list[dict]:
    stmt = select(Project).where(Project.status.in_(["ACTIVE", "PENDING"]))
    from app.core.scope import scope_condition

    condition = scope_condition(ctx, Project, project_attr="id")
    if condition is not None:
        stmt = stmt.where(condition)
    projects = list(db.execute(stmt.order_by(Project.id.desc()).limit(limit)).scalars().all())
    result = []
    for project in projects:
        delay = 0
        if project.plan_end:
            delay = (today() - project.plan_end).days
        result.append(
            {
                "id": project.id,
                "no": project.no,
                "name": project.name,
                "stage": project.stage,
                "status": project.status,
                "progress": project.progress,
                "plan_end": project.plan_end,
                "delay_days": max(delay, 0),
                "budget_amount": float(project.budget_amount or 0),
            }
        )
    return result


def dashboard(db: Session, ctx: ScopeContext) -> dict:
    return {
        "counts": personal_counts(db, ctx),
        "overview": metrics.overview(db, ctx, year=today().year),
        "recent_tasks": recent_tasks(db, ctx),
        "recent_notifications": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "type": item.type,
                "link": item.link,
                "read_at": item.read_at,
                "created_at": item.created_at,
            }
            for item in recent_notifications(db, ctx)
        ],
        "projects": project_health(db, ctx),
        "risks": (vendor_risks(db, ctx)[:10] + contract_risks(db, ctx)[:10]),
    }


def license_alerts(db: Session, company_id: int, days: int = 45) -> list[dict]:
    from datetime import timedelta

    deadline = today() + timedelta(days=days)
    rows = db.execute(
        select(VendorLicense).where(
            VendorLicense.company_id == company_id,
            VendorLicense.valid_to.is_not(None),
            VendorLicense.valid_to <= deadline,
        )
    ).scalars().all()
    result = []
    for item in rows:
        if item.valid_to is None:
            continue
        remain = (item.valid_to - today()).days
        result.append(
            {
                "vendor_id": item.vendor_id,
                "license_id": item.id,
                "name": item.name,
                "valid_to": item.valid_to,
                "days": remain,
                "level": "HIGH" if remain < 15 else "MEDIUM",
                "message": f"证照「{item.name}」将于 {item.valid_to} 到期（剩余 {remain} 天）",
            }
        )
    return result
