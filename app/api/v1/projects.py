"""项目管理：立项、WBS、任务、里程碑、变更、问题/风险、验收、归档与关闭。"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import file_brief, to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import Dept, SysFile, User
from app.models.platform import Customer
from app.models.project import Project
from app.schemas.common import (
    AcceptanceIn,
    ArchiveIn,
    ChangeIn,
    CloseProjectIn,
    InitiationIn,
    IssueIn,
    IssueUpdateIn,
    MemberIn,
    MilestoneCompleteIn,
    MilestoneIn,
    ProjectIn,
    ProjectReportIn,
    ProjectUpdateIn,
    TaskIn,
    TaskUpdateIn,
    WBSIn,
    WBSUpdateIn,
)
from app.services.project import acceptance as acceptance_service
from app.services.project import change as change_service
from app.services.project import execution as execution_service
from app.services.project import project as project_service
from app.services.project import wbs as wbs_service
from app.services.report import pnl as pnl_service

router = APIRouter(prefix="/projects", tags=["项目管理"])

VIEW = Depends(require_permission("project:view"))
MANAGE = Depends(require_permission("project:manage"))
CREATE = Depends(require_permission("project:create"))
CHANGE = Depends(require_permission("project:change"))
ACCEPT = Depends(require_permission("project:acceptance"))
CLOSE = Depends(require_permission("project:close"))


# ------------------------------------------------------------------ 序列化辅助
def _names(db, user_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in user_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.real_name).where(User.id.in_(ids))).all()
    return {int(uid): name for uid, name in rows}


def _project_brief(db, project_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in project_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Project.id, Project.name).where(Project.id.in_(ids))).all()
    return {int(pid): name for pid, name in rows}


def _files(db, file_ids: Iterable[int | None]) -> dict[int, dict]:
    ids = {int(item) for item in file_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(SysFile).where(SysFile.id.in_(ids))).scalars().all()
    return {item.id: file_brief(item) for item in rows}


def _project_row(db, project: Project) -> dict:
    data = to_dict(project)
    names = _names(db, [project.manager_id, project.creator_id])
    data["manager_name"] = names.get(project.manager_id, "")
    data["creator_name"] = names.get(project.creator_id or 0, "")
    dept = db.get(Dept, project.dept_id) if project.dept_id else None
    data["dept_name"] = dept.name if dept else ""
    customer = db.get(Customer, project.customer_id) if project.customer_id else None
    data["customer_name"] = customer.name if customer else ""
    return data


def _wbs_tree(items: list) -> list[dict]:
    nodes = {item.id: {**to_dict(item), "children": []} for item in items}
    roots: list[dict] = []
    for item in items:
        node = nodes[item.id]
        parent = nodes.get(item.parent_id or -1)
        if parent is not None and item.parent_id:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


# ------------------------------------------------------------------ 项目主档
@router.get("", summary="项目列表", dependencies=[VIEW])
def list_projects(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    stage: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    manager_id: int | None = None,
    dept_id: int | None = None,
) -> dict:
    result = project_service.list_projects(
        db,
        ctx,
        params,
        stage=stage,
        status=status,
        keyword=keyword,
        manager_id=manager_id,
        dept_id=dept_id,
    )
    items = [_project_row(db, item) for item in result["items"]]
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("", summary="创建项目（草稿）", dependencies=[CREATE])
def create_project(payload: ProjectIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.create_project(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(_project_row(db, project), "项目已创建")


@router.get("/{project_id}", summary="项目详情", dependencies=[VIEW])
def get_project(project_id: int, db: DbSession, ctx: Scope) -> dict:
    project = project_service.get_project(db, ctx, project_id)
    data = _project_row(db, project)
    initiation = project_service.get_initiation(db, ctx, project.id)
    data["initiation"] = to_dict(initiation) if initiation else None
    members = project_service.list_members(db, ctx, project.id)
    names = _names(db, (member.user_id for member in members))
    data["members"] = [
        {**to_dict(member), "user_name": names.get(member.user_id, "")} for member in members
    ]
    data["deviation"] = project_service.project_deviation(db, ctx, project.id)
    return ok(data)


@router.put("/{project_id}", summary="更新项目", dependencies=[MANAGE])
def update_project(project_id: int, payload: ProjectUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.update_project(
        db, user, ctx, project_id, payload.model_dump(exclude_unset=True)
    )
    return ok(_project_row(db, project), "项目已更新")


# ------------------------------------------------------------------ 立项
@router.get("/{project_id}/initiation", summary="项目立项申请", dependencies=[VIEW])
def get_initiation(project_id: int, db: DbSession, ctx: Scope) -> dict:
    project = project_service.get_project(db, ctx, project_id)
    initiation = project_service.get_initiation(db, ctx, project.id)
    return ok(to_dict(initiation) if initiation else None)


@router.post("/initiations", summary="发起项目立项（可同步创建项目）", dependencies=[CREATE])
def create_initiation(payload: InitiationIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    initiation = project_service.create_initiation(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(initiation), "立项申请已提交" if payload.submit else "立项草稿已保存")


@router.post(
    "/initiations/{initiation_id}/submit",
    summary="提交立项审批",
    dependencies=[CREATE],
)
def submit_initiation(initiation_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    initiation = project_service.submit_initiation(db, user, ctx, initiation_id)
    return ok(to_dict(initiation), "立项审批已提交")


# ------------------------------------------------------------------ 阶段
@router.post("/{project_id}/confirm-plan", summary="确认项目计划并生成基线", dependencies=[MANAGE])
def confirm_plan(project_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.confirm_plan(db, user, ctx, project_id)
    return ok(_project_row(db, project), "项目计划已确认")


@router.post("/{project_id}/start-execution", summary="进入执行阶段", dependencies=[MANAGE])
def start_execution(project_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.start_execution(db, user, ctx, project_id)
    return ok(_project_row(db, project), "项目已进入执行阶段")


@router.get("/{project_id}/baseline", summary="项目计划基线", dependencies=[VIEW])
def list_baseline(
    project_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    rows = project_service.baseline_list(db, ctx, project_id, limit=limit)
    return ok([to_dict(item) for item in rows])


@router.get("/{project_id}/deviation", summary="项目进度/成本偏差", dependencies=[VIEW])
def project_deviation(project_id: int, db: DbSession, ctx: Scope) -> dict:
    return ok(project_service.project_deviation(db, ctx, project_id))


# ------------------------------------------------------------------ 关闭 / 归档
@router.get("/{project_id}/close-check", summary="项目关闭校验", dependencies=[CLOSE])
def close_check(project_id: int, db: DbSession, ctx: Scope) -> dict:
    return ok(project_service.close_check(db, ctx, project_id))


@router.post("/{project_id}/close", summary="关闭项目（支持强制关闭）", dependencies=[CLOSE])
def close_project(project_id: int, payload: CloseProjectIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.close_project(
        db, user, ctx, project_id, force=payload.force, reason=payload.reason
    )
    return ok(_project_row(db, project), "项目已关闭")


@router.post("/{project_id}/archive", summary="归档项目", dependencies=[CLOSE])
def archive_project(project_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project = project_service.archive_project(db, user, ctx, project_id)
    return ok(_project_row(db, project), "项目已归档")


@router.get("/{project_id}/archives", summary="项目归档资料", dependencies=[VIEW])
def list_archives(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = project_service.list_archives(db, ctx, project_id)
    file_map = _files(db, (row.file_id for row in rows if row.file_id))
    names = _names(db, (row.archived_by for row in rows if row.archived_by))
    items = []
    for row in rows:
        data = to_dict(row)
        data["file"] = file_map.get(row.file_id or 0, {})
        data["archived_by_name"] = names.get(row.archived_by or 0, "")
        items.append(data)
    return ok(items)


@router.post("/{project_id}/archives", summary="添加归档资料", dependencies=[MANAGE])
def add_archive(project_id: int, payload: ArchiveIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = project_service.add_archive(
        db, user, ctx, project_id, payload.doc_type, payload.file_id
    )
    return ok(to_dict(item), "归档资料已添加")


# ------------------------------------------------------------------ 成员
@router.get("/{project_id}/members", summary="项目成员", dependencies=[VIEW])
def list_members(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = project_service.list_members(db, ctx, project_id)
    names = _names(db, (row.user_id for row in rows))
    return ok([{**to_dict(row), "user_name": names.get(row.user_id, "")} for row in rows])


@router.post("/{project_id}/members", summary="添加项目成员", dependencies=[MANAGE])
def add_member(project_id: int, payload: MemberIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = project_service.add_member(db, user, ctx, project_id, payload.user_id, payload.role)
    return ok(to_dict(item), "成员已添加")


@router.delete("/{project_id}/members/{member_id}", summary="移除项目成员", dependencies=[MANAGE])
def remove_member(project_id: int, member_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    project_service.remove_member(db, user, ctx, project_id, member_id)
    return ok(None, "成员已移除")


# ------------------------------------------------------------------ WBS
@router.get("/{project_id}/wbs", summary="WBS 列表（含树）", dependencies=[VIEW])
def list_wbs(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = wbs_service.list_wbs(db, ctx, project_id)
    names = _names(db, (row.owner_id for row in rows if row.owner_id))
    items = []
    for row in rows:
        data = to_dict(row)
        data["owner_name"] = names.get(row.owner_id or 0, "")
        items.append(data)
    return ok({"items": items, "tree": _wbs_tree(rows)})


@router.post("/{project_id}/wbs", summary="新增 WBS", dependencies=[MANAGE])
def create_wbs(project_id: int, payload: WBSIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = wbs_service.create_wbs(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "WBS 已创建")


@router.put("/wbs/{wbs_id}", summary="修改 WBS", dependencies=[MANAGE])
def update_wbs(wbs_id: int, payload: WBSUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = wbs_service.update_wbs(db, user, ctx, wbs_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "WBS 已更新")


@router.delete("/wbs/{wbs_id}", summary="删除 WBS", dependencies=[MANAGE])
def delete_wbs(wbs_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    wbs_service.delete_wbs(db, user, ctx, wbs_id)
    return ok(None, "WBS 已删除")


# ------------------------------------------------------------------ 任务
@router.get("/{project_id}/tasks", summary="任务列表", dependencies=[VIEW])
def list_tasks(
    project_id: int,
    db: DbSession,
    ctx: Scope,
    wbs_id: int | None = None,
    status: str | None = None,
    owner_id: int | None = None,
) -> dict:
    rows = wbs_service.list_tasks(db, ctx, project_id, wbs_id=wbs_id, status=status, owner_id=owner_id)
    names = _names(db, (row.owner_id for row in rows if row.owner_id))
    return ok([{**to_dict(row), "owner_name": names.get(row.owner_id or 0, "")} for row in rows])


@router.post("/{project_id}/tasks", summary="新增任务", dependencies=[MANAGE])
def create_task(project_id: int, payload: TaskIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = wbs_service.create_task(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "任务已创建")


@router.put("/tasks/{task_id}", summary="修改任务", dependencies=[MANAGE])
def update_task(task_id: int, payload: TaskUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = wbs_service.update_task(db, user, ctx, task_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "任务已更新")


@router.delete("/tasks/{task_id}", summary="删除任务", dependencies=[MANAGE])
def delete_task(task_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    wbs_service.delete_task(db, user, ctx, task_id)
    return ok(None, "任务已删除")


# ------------------------------------------------------------------ 里程碑
@router.get("/{project_id}/milestones", summary="里程碑列表", dependencies=[VIEW])
def list_milestones(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = execution_service.list_milestones(db, ctx, project_id)
    file_map = _files(db, (row.acceptance_file_id for row in rows if row.acceptance_file_id))
    items = []
    for row in rows:
        data = to_dict(row)
        data["acceptance_file"] = file_map.get(row.acceptance_file_id or 0, {})
        items.append(data)
    return ok(items)


@router.post("/{project_id}/milestones", summary="新增里程碑", dependencies=[MANAGE])
def create_milestone(project_id: int, payload: MilestoneIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.create_milestone(
        db, user, ctx, project_id, payload.model_dump(exclude_unset=True)
    )
    return ok(to_dict(item), "里程碑已创建")


@router.post("/milestones/{milestone_id}/complete", summary="完成里程碑", dependencies=[MANAGE])
def complete_milestone(
    milestone_id: int, payload: MilestoneCompleteIn, db: DbSession, user: CurrentUser, ctx: Scope
) -> dict:
    item = execution_service.complete_milestone(
        db, user, ctx, milestone_id, payload.model_dump(exclude_unset=True)
    )
    return ok(to_dict(item), "里程碑已完成")


@router.delete("/milestones/{milestone_id}", summary="删除里程碑", dependencies=[MANAGE])
def delete_milestone(milestone_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    execution_service.delete_milestone(db, user, ctx, milestone_id)
    return ok(None, "里程碑已删除")


# ------------------------------------------------------------------ 变更
@router.get("/{project_id}/changes", summary="变更记录", dependencies=[VIEW])
def list_changes(
    project_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    rows = change_service.list_changes(db, ctx, project_id, limit=limit)
    names = _names(db, (row.applicant_id for row in rows))
    return ok([{**to_dict(row), "applicant_name": names.get(row.applicant_id, "")} for row in rows])


@router.post("/{project_id}/changes", summary="发起项目变更", dependencies=[CHANGE])
def create_change(project_id: int, payload: ChangeIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = change_service.create_change(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "变更申请已提交")


# ------------------------------------------------------------------ 问题 / 风险
@router.get("/{project_id}/issues", summary="问题列表", dependencies=[VIEW])
def list_issues(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = execution_service.list_issues(db, ctx, project_id)
    names = _names(db, (row.owner_id for row in rows if row.owner_id))
    return ok([{**to_dict(row), "owner_name": names.get(row.owner_id or 0, "")} for row in rows])


@router.post("/{project_id}/issues", summary="新增问题", dependencies=[MANAGE])
def create_issue(project_id: int, payload: IssueIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.create_issue(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "问题已登记")


@router.put("/issues/{issue_id}", summary="更新问题", dependencies=[MANAGE])
def update_issue(issue_id: int, payload: IssueUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.update_issue(db, user, ctx, issue_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "问题已更新")


@router.get("/{project_id}/risks", summary="风险列表", dependencies=[VIEW])
def list_risks(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = execution_service.list_risks(db, ctx, project_id)
    names = _names(db, (row.owner_id for row in rows if row.owner_id))
    return ok([{**to_dict(row), "owner_name": names.get(row.owner_id or 0, "")} for row in rows])


@router.post("/{project_id}/risks", summary="新增风险", dependencies=[MANAGE])
def create_risk(project_id: int, payload: IssueIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.create_risk(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "风险已登记")


@router.put("/risks/{risk_id}", summary="更新风险", dependencies=[MANAGE])
def update_risk(risk_id: int, payload: IssueUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.update_risk(db, user, ctx, risk_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "风险已更新")


# ------------------------------------------------------------------ 周报
@router.get("/{project_id}/reports", summary="项目周报/月报", dependencies=[VIEW])
def list_reports(project_id: int, db: DbSession, ctx: Scope) -> dict:
    rows = execution_service.list_reports(db, ctx, project_id)
    names = _names(db, (row.reporter_id for row in rows))
    return ok([{**to_dict(row), "reporter_name": names.get(row.reporter_id, "")} for row in rows])


@router.post("/{project_id}/reports", summary="提交项目周报/月报", dependencies=[MANAGE])
def create_report(project_id: int, payload: ProjectReportIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = execution_service.create_report(db, user, ctx, project_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "报告已提交")


# ------------------------------------------------------------------ 验收
@router.get("/{project_id}/acceptances", summary="验收单列表", dependencies=[VIEW])
def list_acceptances(
    project_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    rows = acceptance_service.list_acceptances(db, ctx, project_id, limit=limit)
    names = _names(db, (row.applicant_id for row in rows))
    file_map = _files(db, (row.sign_file_id for row in rows if row.sign_file_id))
    items = []
    for row in rows:
        data = to_dict(row)
        data["applicant_name"] = names.get(row.applicant_id, "")
        data["sign_file"] = file_map.get(row.sign_file_id or 0, {})
        items.append(data)
    return ok(items)


@router.post("/{project_id}/acceptances", summary="提交项目验收", dependencies=[ACCEPT])
def create_acceptance(project_id: int, payload: AcceptanceIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = acceptance_service.create_acceptance(
        db, user, ctx, project_id, payload.model_dump(exclude_unset=True)
    )
    return ok(to_dict(item), "验收申请已提交")


@router.get("/acceptances/{acceptance_id}", summary="验收单详情", dependencies=[VIEW])
def get_acceptance(acceptance_id: int, db: DbSession, ctx: Scope) -> dict:
    item = acceptance_service.get_acceptance(db, ctx, acceptance_id)
    data = to_dict(item)
    names = _names(db, [item.applicant_id])
    data["applicant_name"] = names.get(item.applicant_id, "")
    data["sign_file"] = _files(db, [item.sign_file_id] if item.sign_file_id else []).get(
        item.sign_file_id or 0, {}
    )
    return ok(data)


# ------------------------------------------------------------------ 项目损益
@router.get("/{project_id}/pnl", summary="项目损益明细", dependencies=[VIEW])
def project_pnl(project_id: int, db: DbSession, ctx: Scope) -> dict:
    return ok(pnl_service.project_pnl_detail(db, ctx, project_id))
