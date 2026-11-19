from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext
from app.models.iam import User
from app.models.project import Issue, Milestone, ProjectReport, Risk
from app.services.common import ensure_files
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.services.project.project import get_project
from app.utils.datetime import to_date, today

LEVELS = {"LOW", "MEDIUM", "HIGH", "URGENT"}
ISSUE_STATUSES = {"OPEN", "PROCESSING", "CLOSED"}


# ---------------------------------------------------------------- 里程碑
def list_milestones(db: Session, ctx: ScopeContext, project_id: int) -> list[Milestone]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(
            select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.plan_date, Milestone.id)
        )
        .scalars()
        .all()
    )


def create_milestone(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Milestone:
    project = get_project(db, ctx, project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增里程碑")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("里程碑名称不能为空")
    plan_date = to_date(payload.get("plan_date"))
    if not plan_date:
        raise BusinessRuleError("请填写里程碑计划日期")
    file_id = payload.get("acceptance_file_id")
    if file_id:
        ensure_files(db, [int(file_id)], project.company_id)
    item = Milestone(
        company_id=project.company_id,
        project_id=project.id,
        name=name[:255],
        plan_date=plan_date,
        status="PENDING",
        acceptance_file_id=int(file_id) if file_id else None,
    )
    db.add(item)
    db.flush()
    write_audit(
        db, user=user, action="CREATE_MILESTONE", target_type="MILESTONE", target_id=item.id, after=snapshot(item)
    )
    return item


def complete_milestone(
    db: Session, user: User, ctx: ScopeContext, milestone_id: int, payload: dict[str, Any]
) -> Milestone:
    item = db.get(Milestone, milestone_id)
    if item is None:
        raise NotFoundError("里程碑不存在")
    project = get_project(db, ctx, item.project_id)
    if item.status == "DONE":
        raise BusinessRuleError("里程碑已完成")
    item.actual_date = to_date(payload.get("actual_date")) or today()
    item.status = "DONE"
    file_id = payload.get("acceptance_file_id")
    if file_id:
        ensure_files(db, [int(file_id)], project.company_id)
        item.acceptance_file_id = int(file_id)
    db.flush()
    write_audit(
        db,
        user=user,
        action="COMPLETE_MILESTONE",
        target_type="MILESTONE",
        target_id=item.id,
        after={"actual_date": str(item.actual_date)},
    )
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=[project.manager_id],
        title=f"里程碑达成：{project.name} / {item.name}",
        content=f"里程碑「{item.name}」已于 {item.actual_date} 完成。",
        type="SYSTEM",
        biz_type="PROJECT",
        biz_id=project.id,
        link=f"/projects/{project.id}?tab=milestones",
        email=False,
    )
    return item


def delete_milestone(db: Session, user: User, ctx: ScopeContext, milestone_id: int) -> None:
    item = db.get(Milestone, milestone_id)
    if item is None:
        raise NotFoundError("里程碑不存在")
    project = get_project(db, ctx, item.project_id)
    if project.stage in {"CLOSE", "ARCHIVED"}:
        raise BusinessRuleError("项目收尾阶段不能删除里程碑")
    db.delete(item)
    db.flush()
    write_audit(db, user=user, action="DELETE_MILESTONE", target_type="MILESTONE", target_id=milestone_id)


# ---------------------------------------------------------------- 问题 / 风险
def _list_issue_like(db: Session, ctx: ScopeContext, project_id: int, model) -> list:
    get_project(db, ctx, project_id)
    return list(
        db.execute(
            select(model).where(model.project_id == project_id).order_by(model.status, model.due_date, model.id)
        )
        .scalars()
        .all()
    )


def _create_issue_like(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any], model):
    project = get_project(db, ctx, project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增问题/风险")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise BusinessRuleError("标题不能为空")
    level = str(payload.get("level") or "MEDIUM")
    if level not in LEVELS:
        raise BusinessRuleError("等级非法")
    owner_id = payload.get("owner_id")
    if owner_id:
        owner = db.get(User, int(owner_id))
        if owner is None or owner.company_id != project.company_id:
            raise BusinessRuleError("责任人不存在")
    item = model(
        company_id=project.company_id,
        project_id=project.id,
        title=title[:255],
        level=level,
        owner_id=int(owner_id) if owner_id else user.id,
        due_date=to_date(payload.get("due_date")),
        status="OPEN",
        solution=(payload.get("solution") or "")[:2000] or None,
        creator_id=user.id,
    )
    db.add(item)
    db.flush()
    write_audit(
        db,
        user=user,
        action=f"CREATE_{model.__tablename__.upper()}",
        target_type=model.__tablename__.upper(),
        target_id=item.id,
        after=snapshot(item),
    )
    return item


def _update_issue_like(db: Session, user: User, ctx: ScopeContext, item_id: int, payload: dict[str, Any], model):
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError("记录不存在")
    get_project(db, ctx, item.project_id)
    before = snapshot(item)
    if payload.get("title") is not None and str(payload["title"]).strip():
        item.title = str(payload["title"]).strip()[:255]
    if payload.get("level") is not None:
        if payload["level"] not in LEVELS:
            raise BusinessRuleError("等级非法")
        item.level = payload["level"]
    if payload.get("owner_id") is not None:
        owner = db.get(User, int(payload["owner_id"])) if payload["owner_id"] else None
        if owner is None or owner.company_id != item.company_id:
            raise BusinessRuleError("责任人不存在")
        item.owner_id = owner.id
    if payload.get("due_date") is not None:
        item.due_date = to_date(payload["due_date"])
    if payload.get("solution") is not None:
        item.solution = str(payload["solution"])[:2000]
    if payload.get("status") is not None:
        status = str(payload["status"])
        if status not in ISSUE_STATUSES:
            raise BusinessRuleError("状态非法")
        if status == "CLOSED" and not (item.solution or payload.get("solution")):
            raise BusinessRuleError("关闭前请填写解决方案")
        item.status = status
    db.flush()
    write_audit(
        db,
        user=user,
        action=f"UPDATE_{model.__tablename__.upper()}",
        target_type=model.__tablename__.upper(),
        target_id=item.id,
        before=before,
        after=snapshot(item),
    )
    return item


def list_issues(db: Session, ctx: ScopeContext, project_id: int) -> list[Issue]:
    return _list_issue_like(db, ctx, project_id, Issue)


def create_issue(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Issue:
    return _create_issue_like(db, user, ctx, project_id, payload, Issue)


def update_issue(db: Session, user: User, ctx: ScopeContext, issue_id: int, payload: dict[str, Any]) -> Issue:
    return _update_issue_like(db, user, ctx, issue_id, payload, Issue)


def list_risks(db: Session, ctx: ScopeContext, project_id: int) -> list[Risk]:
    return _list_issue_like(db, ctx, project_id, Risk)


def create_risk(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Risk:
    return _create_issue_like(db, user, ctx, project_id, payload, Risk)


def update_risk(db: Session, user: User, ctx: ScopeContext, risk_id: int, payload: dict[str, Any]) -> Risk:
    return _update_issue_like(db, user, ctx, risk_id, payload, Risk)


# ---------------------------------------------------------------- 周报 / 月报
def list_reports(db: Session, ctx: ScopeContext, project_id: int) -> list[ProjectReport]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(
            select(ProjectReport)
            .where(ProjectReport.project_id == project_id)
            .order_by(ProjectReport.id.desc())
        )
        .scalars()
        .all()
    )


def create_report(
    db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]
) -> ProjectReport:
    project = get_project(db, ctx, project_id)
    report_type = str(payload.get("type") or "WEEKLY")
    if report_type not in {"WEEKLY", "MONTHLY"}:
        raise BusinessRuleError("报告类型非法")
    period = str(payload.get("period") or "").strip()
    if not period:
        raise BusinessRuleError("请填写报告期间")
    content = str(payload.get("content") or "").strip()
    if len(content) < 10:
        raise BusinessRuleError("报告内容不得少于 10 个字")
    raw_progress = payload.get("progress")
    if raw_progress is None:
        raw_progress = project.progress
    progress = int(raw_progress or 0)
    if progress < 0 or progress > 100:
        raise BusinessRuleError("进度必须在 0-100 之间")
    item = ProjectReport(
        company_id=project.company_id,
        project_id=project.id,
        type=report_type,
        period=period[:16],
        progress=progress,
        content=content[:20000],
        issues=(payload.get("issues") or "")[:5000],
        next_plan=(payload.get("next_plan") or "")[:5000],
        reporter_id=user.id,
    )
    db.add(item)
    db.flush()
    write_audit(
        db, user=user, action="CREATE_PROJECT_REPORT", target_type="PROJECT_REPORT", target_id=item.id
    )
    return item


def milestone_rate(db: Session, project_id: int) -> float:
    total = int(db.execute(select(func.count(Milestone.id)).where(Milestone.project_id == project_id)).scalar_one())
    if total == 0:
        return 0.0
    done = int(
        db.execute(
            select(func.count(Milestone.id)).where(Milestone.project_id == project_id, Milestone.status == "DONE")
        ).scalar_one()
    )
    return round(done / total, 4)
