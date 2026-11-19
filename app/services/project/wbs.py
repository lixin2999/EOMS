from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.scope import ScopeContext
from app.models.iam import User
from app.models.project import WBS, Project, ProjectMember, Task
from app.services.iam.audit import snapshot, write_audit
from app.services.project.project import get_project
from app.utils.datetime import to_date, today
from app.utils.money import to_decimal

TASK_STATUSES = {"TODO", "DOING", "DONE", "BLOCKED"}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}


def _validate_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise BusinessRuleError("结束日期不能早于开始日期")


def _validate_owner(db: Session, project: Project, user_id: int | None) -> User | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or user.company_id != project.company_id or user.status != "ACTIVE":
        raise BusinessRuleError("责任人不存在或已停用")
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    ).scalar_one_or_none()
    if member is None:
        raise BusinessRuleError("责任人不是项目成员，请先加入项目成员")
    return user


def recalc_progress(db: Session, project_id: int) -> None:
    project = db.get(Project, project_id)
    if project is None:
        return
    tasks = list(db.execute(select(Task).where(Task.project_id == project_id)).scalars().all())
    if tasks:
        project.progress = int(round(sum(task.progress for task in tasks) / len(tasks)))
    wbs_rows = list(db.execute(select(WBS).where(WBS.project_id == project_id)).scalars().all())
    for wbs in wbs_rows:
        children = [task for task in tasks if task.wbs_id == wbs.id]
        if children:
            wbs.progress = int(round(sum(task.progress for task in children) / len(children)))
    db.flush()


# ---------------------------------------------------------------- WBS
def list_wbs(db: Session, ctx: ScopeContext, project_id: int) -> list[WBS]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(select(WBS).where(WBS.project_id == project_id).order_by(WBS.code, WBS.sort, WBS.id))
        .scalars()
        .all()
    )


def create_wbs(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> WBS:
    project = get_project(db, ctx, project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增 WBS")
    parent = None
    parent_id = payload.get("parent_id")
    if parent_id:
        parent = db.get(WBS, int(parent_id))
        if parent is None or parent.project_id != project.id:
            raise BusinessRuleError("上级 WBS 不存在")
        if parent.level >= 5:
            raise BusinessRuleError("WBS 层级不得超过 5 级")
    plan_start = to_date(payload.get("plan_start"))
    plan_end = to_date(payload.get("plan_end"))
    _validate_dates(plan_start, plan_end)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("WBS 名称不能为空")
    owner = _validate_owner(db, project, payload.get("owner_id"))
    sibling_count = int(
        db.execute(
            select(func.count(WBS.id)).where(
                WBS.project_id == project.id,
                WBS.parent_id == (parent.id if parent else None),
            )
        ).scalar_one()
    )
    code = f"{parent.code}.{sibling_count + 1}" if parent else str(sibling_count + 1)
    wbs = WBS(
        company_id=project.company_id,
        project_id=project.id,
        parent_id=parent.id if parent else None,
        code=code,
        name=name[:255],
        level=(parent.level + 1) if parent else 1,
        owner_id=owner.id if owner else None,
        plan_start=plan_start,
        plan_end=plan_end,
        progress=0,
        is_milestone=bool(payload.get("is_milestone")),
        sort=sibling_count,
    )
    db.add(wbs)
    db.flush()
    write_audit(
        db, user=user, action="CREATE_WBS", target_type="WBS", target_id=wbs.id, after=snapshot(wbs)
    )
    return wbs


def update_wbs(db: Session, user: User, ctx: ScopeContext, wbs_id: int, payload: dict[str, Any]) -> WBS:
    wbs = db.get(WBS, wbs_id)
    if wbs is None:
        raise NotFoundError("WBS 不存在")
    project = get_project(db, ctx, wbs.project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能修改 WBS")
    before = snapshot(wbs)
    if payload.get("name") is not None and str(payload["name"]).strip():
        wbs.name = str(payload["name"]).strip()[:255]
    if payload.get("owner_id") is not None:
        owner = _validate_owner(db, project, payload["owner_id"])
        wbs.owner_id = owner.id if owner else None
    if payload.get("plan_start") is not None:
        wbs.plan_start = to_date(payload["plan_start"])
    if payload.get("plan_end") is not None:
        wbs.plan_end = to_date(payload["plan_end"])
    _validate_dates(wbs.plan_start, wbs.plan_end)
    if payload.get("is_milestone") is not None:
        wbs.is_milestone = bool(payload["is_milestone"])
    if payload.get("sort") is not None:
        wbs.sort = int(payload["sort"])
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_WBS",
        target_type="WBS",
        target_id=wbs.id,
        before=before,
        after=snapshot(wbs),
    )
    return wbs


def delete_wbs(db: Session, user: User, ctx: ScopeContext, wbs_id: int) -> None:
    wbs = db.get(WBS, wbs_id)
    if wbs is None:
        raise NotFoundError("WBS 不存在")
    project = get_project(db, ctx, wbs.project_id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能删除 WBS")
    children = int(db.execute(select(func.count(WBS.id)).where(WBS.parent_id == wbs.id)).scalar_one())
    tasks = int(db.execute(select(func.count(Task.id)).where(Task.wbs_id == wbs.id)).scalar_one())
    if children or tasks:
        raise BusinessRuleError("请先删除子 WBS 与关联任务")
    db.delete(wbs)
    db.flush()
    write_audit(db, user=user, action="DELETE_WBS", target_type="WBS", target_id=wbs_id, before=snapshot(wbs))


# ---------------------------------------------------------------- 任务
def list_tasks(
    db: Session,
    ctx: ScopeContext,
    project_id: int,
    *,
    wbs_id: int | None = None,
    status: str | None = None,
    owner_id: int | None = None,
) -> list[Task]:
    get_project(db, ctx, project_id)
    stmt = select(Task).where(Task.project_id == project_id)
    if wbs_id:
        stmt = stmt.where(Task.wbs_id == wbs_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if owner_id:
        stmt = stmt.where(Task.owner_id == owner_id)
    return list(db.execute(stmt.order_by(Task.plan_start, Task.id)).scalars().all())


def get_task(db: Session, ctx: ScopeContext, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    get_project(db, ctx, task.project_id)
    return task


def create_task(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Task:
    project = get_project(db, ctx, project_id)
    if project.status in {"CLOSED", "CANCELED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增任务")
    if project.stage == "LAUNCH":
        project.stage = "PLAN"
    wbs_id = payload.get("wbs_id")
    if wbs_id:
        wbs = db.get(WBS, int(wbs_id))
        if wbs is None or wbs.project_id != project.id:
            raise BusinessRuleError("WBS 不属于该项目")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("任务名称不能为空")
    plan_start = to_date(payload.get("plan_start"))
    plan_end = to_date(payload.get("plan_end"))
    _validate_dates(plan_start, plan_end)
    owner = _validate_owner(db, project, payload.get("owner_id"))
    status = str(payload.get("status") or "TODO")
    if status not in TASK_STATUSES:
        raise BusinessRuleError("任务状态非法")
    priority = str(payload.get("priority") or "MEDIUM")
    if priority not in PRIORITIES:
        raise BusinessRuleError("任务优先级非法")
    progress = int(payload.get("progress") or 0)
    if progress < 0 or progress > 100:
        raise BusinessRuleError("任务进度必须在 0-100 之间")
    if status == "DONE":
        progress = 100
    task = Task(
        company_id=project.company_id,
        wbs_id=int(wbs_id) if wbs_id else None,
        project_id=project.id,
        name=name[:255],
        owner_id=owner.id if owner else None,
        plan_start=plan_start,
        plan_end=plan_end,
        progress=progress,
        status=status,
        priority=priority,
        estimate_hours=to_decimal(payload.get("estimate_hours"), field_name="预估工时"),
    )
    db.add(task)
    db.flush()
    recalc_progress(db, project.id)
    write_audit(db, user=user, action="CREATE_TASK", target_type="TASK", target_id=task.id, after=snapshot(task))
    return task


def update_task(db: Session, user: User, ctx: ScopeContext, task_id: int, payload: dict[str, Any]) -> Task:
    task = get_task(db, ctx, task_id)
    project = db.get(Project, task.project_id)
    if project is None or project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能修改任务")
    if payload.get("version") is not None and int(payload["version"]) != task.version:
        raise ConflictError("任务已被他人更新，请刷新后重试")
    before = snapshot(task)
    if payload.get("name") is not None and str(payload["name"]).strip():
        task.name = str(payload["name"]).strip()[:255]
    if payload.get("owner_id") is not None:
        owner = _validate_owner(db, project, payload["owner_id"])
        task.owner_id = owner.id if owner else None
    if payload.get("plan_start") is not None:
        task.plan_start = to_date(payload["plan_start"])
    if payload.get("plan_end") is not None:
        task.plan_end = to_date(payload["plan_end"])
    _validate_dates(task.plan_start, task.plan_end)
    if payload.get("priority") is not None:
        if payload["priority"] not in PRIORITIES:
            raise BusinessRuleError("任务优先级非法")
        task.priority = payload["priority"]
    if payload.get("estimate_hours") is not None:
        task.estimate_hours = to_decimal(payload["estimate_hours"], field_name="预估工时")
    if payload.get("actual_hours") is not None:
        hours = to_decimal(payload["actual_hours"], field_name="实际工时")
        if hours < 0:
            raise BusinessRuleError("实际工时不能为负数")
        task.actual_hours = hours
    if payload.get("status") is not None:
        status = str(payload["status"])
        if status not in TASK_STATUSES:
            raise BusinessRuleError("任务状态非法")
        task.status = status
        if status == "DONE":
            task.progress = 100
            task.actual_end = to_date(payload.get("actual_end")) or today()
        elif task.status == "DONE" and status != "DONE":
            task.actual_end = None
    if payload.get("progress") is not None:
        progress = int(payload["progress"])
        if progress < 0 or progress > 100:
            raise BusinessRuleError("任务进度必须在 0-100 之间")
        task.progress = progress
        if progress == 100 and task.status != "DONE":
            task.status = "DONE"
            task.actual_end = to_date(payload.get("actual_end")) or today()
    if payload.get("actual_start") is not None:
        task.actual_start = to_date(payload["actual_start"])
    if payload.get("actual_end") is not None:
        task.actual_end = to_date(payload["actual_end"])
    _validate_dates(task.actual_start, task.actual_end)
    task.version = int(task.version or 1) + 1
    db.flush()
    recalc_progress(db, project.id)
    write_audit(
        db,
        user=user,
        action="UPDATE_TASK",
        target_type="TASK",
        target_id=task.id,
        before=before,
        after=snapshot(task),
    )
    return task


def delete_task(db: Session, user: User, ctx: ScopeContext, task_id: int) -> None:
    task = get_task(db, ctx, task_id)
    project = db.get(Project, task.project_id)
    if project and project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能删除任务")
    if project and project.stage in {"PLAN_CONFIRMED", "EXECUTE", "CLOSE"} and not user.is_super:
        raise BusinessRuleError("计划已确认，删除任务需走变更流程")
    db.delete(task)
    db.flush()
    if project:
        recalc_progress(db, project.id)
    write_audit(db, user=user, action="DELETE_TASK", target_type="TASK", target_id=task_id, before=snapshot(task))
