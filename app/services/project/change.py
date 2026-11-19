from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext
from app.models.enums import ChangeType
from app.models.iam import User
from app.models.project import Change, Project
from app.models.workflow import WorkflowInstance
from app.services.iam.audit import write_audit
from app.services.iam.notification import notify_with_email
from app.services.project.project import get_project
from app.utils.datetime import to_date
from app.utils.money import to_decimal
from app.workflow import engine

CHANGE_TYPES = {item.value for item in ChangeType}


def _before(project: Project, change_type: str) -> dict[str, Any]:
    if change_type == ChangeType.BUDGET.value:
        return {"budget_amount": str(project.budget_amount)}
    if change_type == ChangeType.SCHEDULE.value:
        return {
            "plan_start": project.plan_start.isoformat() if project.plan_start else None,
            "plan_end": project.plan_end.isoformat() if project.plan_end else None,
        }
    return {"name": project.name, "description": project.description}


def _validate_after(change_type: str, after: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(after, dict) or not after:
        raise BusinessRuleError("请填写变更后内容")
    if change_type == ChangeType.BUDGET.value:
        amount = to_decimal(after.get("budget_amount"), field_name="变更后预算")
        if amount < 0:
            raise BusinessRuleError("预算不能为负数")
        return {"budget_amount": str(amount)}
    if change_type == ChangeType.SCHEDULE.value:
        start = to_date(after.get("plan_start"))
        end = to_date(after.get("plan_end"))
        if not start or not end:
            raise BusinessRuleError("请填写变更后的计划起止日期")
        if end < start:
            raise BusinessRuleError("计划结束日期不能早于开始日期")
        return {"plan_start": start.isoformat(), "plan_end": end.isoformat()}
    if change_type == ChangeType.SCOPE.value:
        name = str(after.get("name") or "").strip()
        if not name:
            raise BusinessRuleError("请填写变更后项目名称")
        return {"name": name[:255], "description": str(after.get("description") or "")[:2000]}
    raise BusinessRuleError("变更类型非法")


def list_changes(db: Session, ctx: ScopeContext, project_id: int) -> list[Change]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(select(Change).where(Change.project_id == project_id).order_by(Change.id.desc()))
        .scalars()
        .all()
    )


def get_change(db: Session, ctx: ScopeContext, change_id: int) -> Change:
    change = db.get(Change, change_id)
    if change is None:
        raise NotFoundError("变更单不存在")
    get_project(db, ctx, change.project_id)
    return change


def create_change(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Change:
    project = get_project(db, ctx, project_id)
    if project.status in {"CLOSED", "ARCHIVED", "CANCELED", "DRAFT"}:
        raise BusinessRuleError("项目当前状态不允许发起变更")
    change_type = str(payload.get("type") or "")
    if change_type not in CHANGE_TYPES:
        raise BusinessRuleError("变更类型非法")
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise BusinessRuleError("变更原因不得少于 5 个字")
    after = _validate_after(change_type, payload.get("after") or {})
    change = Change(
        company_id=project.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=user.id,
        applicant_id=user.id,
        type=change_type,
        before_json=_before(project, change_type),
        after_json=after,
        reason=reason[:1000],
        status="RUNNING",
    )
    db.add(change)
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        initiator=user,
        def_code="PROJECT_CHANGE",
        biz_type="PROJECT_CHANGE",
        biz_id=change.id,
        title=f"项目变更：{project.no} {project.name}（{change_type}）",
        context={
            "amount": str(after.get("budget_amount") or project.budget_amount or 0),
            "type": change_type,
            "project_id": project.id,
            "project_no": project.no,
        },
    )
    change.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="CREATE_PROJECT_CHANGE",
        target_type="PROJECT_CHANGE",
        target_id=change.id,
        after={"type": change_type, "after": after, "reason": reason},
    )
    return change


def on_change_approved(db: Session, instance: WorkflowInstance) -> None:
    change = db.get(Change, instance.biz_id)
    if change is None:
        raise BusinessRuleError("变更单不存在")
    project = db.get(Project, change.project_id)
    if project is None:
        raise BusinessRuleError("项目不存在")
    after = change.after_json or {}
    if change.type == ChangeType.BUDGET.value:
        project.budget_amount = to_decimal(after.get("budget_amount"), field_name="变更后预算")
    elif change.type == ChangeType.SCHEDULE.value:
        project.plan_start = to_date(after.get("plan_start"))
        project.plan_end = to_date(after.get("plan_end"))
        if project.plan_start and project.plan_end and project.plan_end < project.plan_start:
            raise BusinessRuleError("变更后计划日期不合法")
    elif change.type == ChangeType.SCOPE.value:
        if after.get("name"):
            project.name = str(after["name"])[:255]
        if after.get("description") is not None:
            project.description = str(after["description"])[:2000]
    change.status = "APPROVED"
    project.version = int(project.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=None,
        action="PROJECT_CHANGE_APPROVED",
        target_type="PROJECT_CHANGE",
        target_id=change.id,
        company_id=project.company_id,
        before=change.before_json,
        after=change.after_json,
    )
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=[project.manager_id, change.applicant_id],
        title=f"项目变更通过：{project.name}",
        content=f"变更类型 {change.type} 已审批通过并生效。",
        type="APPROVAL",
        biz_type="PROJECT_CHANGE",
        biz_id=change.id,
        link=f"/projects/{project.id}?tab=changes",
        email=True,
    )


def on_change_rejected(db: Session, instance: WorkflowInstance) -> None:
    change = db.get(Change, instance.biz_id)
    if change and change.status == "RUNNING":
        change.status = "REJECTED"
        db.flush()


def on_change_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    change = db.get(Change, instance.biz_id)
    if change and change.status == "RUNNING":
        change.status = "DRAFT"
        db.flush()
