from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.enums import PaymentStatus, ProjectStage, ProjectStatus
from app.models.finance import Payment
from app.models.iam import User
from app.models.project import (
    WBS,
    Acceptance,
    Archive,
    Initiation,
    Issue,
    Project,
    ProjectMember,
    Task,
    TaskBaseline,
)
from app.models.workflow import WorkflowInstance
from app.services.common import company_code
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now, to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import project_no
from app.workflow import engine

PROJECT_STATUSES = {item.value for item in ProjectStatus}


def project_query(ctx: ScopeContext) -> Select:
    stmt = select(Project)
    condition = scope_condition(ctx, Project, project_attr="id")
    return stmt.where(condition) if condition is not None else stmt


def list_projects(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    stage: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    manager_id: int | None = None,
    dept_id: int | None = None,
) -> dict:
    stmt = project_query(ctx)
    if stage:
        stmt = stmt.where(Project.stage == stage)
    if status:
        stmt = stmt.where(Project.status == status)
    if keyword:
        stmt = stmt.where(or_(Project.name.like(f"%{keyword}%"), Project.no.like(f"%{keyword}%")))
    if manager_id:
        stmt = stmt.where(Project.manager_id == manager_id)
    if dept_id:
        stmt = stmt.where(Project.dept_id == dept_id)
    stmt = stmt.order_by(Project.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_project(db: Session, ctx: ScopeContext, project_id: int) -> Project:
    project = db.execute(project_query(ctx).where(Project.id == project_id)).scalar_one_or_none()
    if project is None:
        raise NotFoundError("项目不存在或无权访问")
    return project


def _check_user(db: Session, user_id: int | None, company_id: int) -> User | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or user.company_id != company_id or user.status != "ACTIVE":
        raise BusinessRuleError("指定人员不存在或已停用")
    return user


def create_project(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Project:
    manager = _check_user(db, payload.get("manager_id") or user.id, user.company_id)
    if manager is None:
        raise BusinessRuleError("请选择项目经理")
    plan_start = to_date(payload.get("plan_start"))
    plan_end = to_date(payload.get("plan_end"))
    if plan_start and plan_end and plan_end < plan_start:
        raise BusinessRuleError("计划结束日期不能早于开始日期")
    project = Project(
        company_id=user.company_id,
        dept_id=payload.get("dept_id") or user.dept_id,
        creator_id=user.id,
        no=project_no(db, company_code(db, user.company_id), today().year),
        name=str(payload.get("name") or "").strip()[:255],
        type=str(payload.get("type") or "OTHER"),
        customer_id=payload.get("customer_id"),
        manager_id=manager.id,
        stage=ProjectStage.LAUNCH.value,
        status=ProjectStatus.DRAFT.value,
        plan_start=plan_start,
        plan_end=plan_end,
        budget_amount=to_decimal(payload.get("budget_amount"), field_name="预算金额"),
        contract_amount=to_decimal(payload.get("contract_amount"), field_name="合同金额"),
        progress=0,
        secret_level=str(payload.get("secret_level") or "INTERNAL"),
        description=(payload.get("description") or "")[:2000],
    )
    if not project.name:
        raise BusinessRuleError("项目名称不能为空")
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            company_id=user.company_id,
            project_id=project.id,
            user_id=manager.id,
            role="PM",
            join_at=today(),
        )
    )
    db.flush()
    write_audit(
        db, user=user, action="CREATE_PROJECT", target_type="PROJECT", target_id=project.id, after=snapshot(project)
    )
    return project


def update_project(db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]) -> Project:
    project = get_project(db, ctx, project_id)
    if project.manager_id != user.id and not user.is_super:
        raise BusinessRuleError("只有项目经理或管理员可修改项目")
    if project.status in {ProjectStatus.CLOSED.value, ProjectStatus.ARCHIVED.value}:
        raise BusinessRuleError("项目已关闭，不能修改")
    expected = payload.get("version")
    if expected is not None and int(expected) != project.version:
        raise ConflictError("项目已被修改，请刷新后重试")
    before = snapshot(project)
    if payload.get("name") is not None and str(payload["name"]).strip():
        project.name = str(payload["name"]).strip()[:255]
    if payload.get("type") is not None:
        project.type = str(payload["type"])
    if payload.get("customer_id") is not None:
        project.customer_id = int(payload["customer_id"]) if payload["customer_id"] else None
    if payload.get("manager_id") is not None:
        manager = _check_user(db, int(payload["manager_id"]), project.company_id)
        if manager is None:
            raise BusinessRuleError("项目经理不存在")
        project.manager_id = manager.id
        exists = db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id, ProjectMember.user_id == manager.id
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                ProjectMember(
                    company_id=project.company_id, project_id=project.id, user_id=manager.id, role="PM", join_at=today()
                )
            )
    if payload.get("description") is not None:
        project.description = str(payload["description"])[:2000]
    if payload.get("secret_level") is not None:
        project.secret_level = str(payload["secret_level"])
    project.version = int(project.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_PROJECT",
        target_type="PROJECT",
        target_id=project.id,
        before=before,
        after=snapshot(project),
    )
    return project


# ---------------------------------------------------------------- 立项
def create_initiation(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Initiation:
    project_id = payload.get("project_id")
    if project_id:
        project = get_project(db, ctx, int(project_id))
        if project.manager_id != user.id and not user.is_super:
            raise BusinessRuleError("只能为本人负责的项目发起立项")
        if project.status not in {ProjectStatus.DRAFT.value, ProjectStatus.CANCELED.value}:
            raise BusinessRuleError("项目当前状态不能发起立项")
    else:
        project = create_project(db, user, ctx, payload)
    exists = db.execute(
        select(Initiation).where(
            Initiation.project_id == project.id,
            Initiation.status.in_(["DRAFT", "RUNNING", "APPROVED"]),
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessRuleError("该项目已存在立项申请")
    initiation = Initiation(
        company_id=user.company_id,
        dept_id=user.dept_id,
        project_id=project.id,
        creator_id=user.id,
        applicant_id=user.id,
        background=(payload.get("background") or "")[:2000],
        goal=(payload.get("goal") or "")[:2000],
        estimate_cost=to_decimal(payload.get("estimate_cost"), field_name="预估成本"),
        estimate_income=to_decimal(payload.get("estimate_income"), field_name="预估收入"),
        risk_desc=(payload.get("risk_desc") or "")[:2000],
        status="DRAFT",
    )
    db.add(initiation)
    db.flush()
    write_audit(
        db,
        user=user,
        action="CREATE_INITIATION",
        target_type="INITIATION",
        target_id=initiation.id,
        after=snapshot(initiation),
    )
    if payload.get("submit", True):
        submit_initiation(db, user, ctx, initiation.id)
    return initiation


def submit_initiation(db: Session, user: User, ctx: ScopeContext, initiation_id: int) -> Initiation:
    initiation = db.get(Initiation, initiation_id)
    if initiation is None or initiation.company_id != user.company_id:
        raise NotFoundError("立项申请不存在")
    project = get_project(db, ctx, initiation.project_id)
    if project.manager_id != user.id and not user.is_super:
        raise BusinessRuleError("只能提交本人负责项目的立项")
    if initiation.status != "DRAFT":
        raise BusinessRuleError("立项申请当前状态不允许提交")
    if not initiation.background or not initiation.goal:
        raise BusinessRuleError("请填写立项背景与目标")
    if initiation.estimate_cost < 0 or initiation.estimate_income < 0:
        raise BusinessRuleError("预估金额不能为负数")
    initiation.status = "RUNNING"
    project.status = ProjectStatus.PENDING.value
    project.stage = ProjectStage.LAUNCH.value
    project.budget_amount = initiation.estimate_cost
    project.contract_amount = initiation.estimate_income
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=initiation.dept_id,
        project_id=project.id,
        initiator=user,
        def_code="PROJECT_INITIATION",
        biz_type="PROJECT_INITIATION",
        biz_id=initiation.id,
        title=f"项目立项：{project.no} {project.name}",
        context={
            "amount": str(initiation.estimate_cost),
            "project_id": project.id,
            "project_no": project.no,
            "project_name": project.name,
        },
    )
    initiation.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="SUBMIT_INITIATION",
        target_type="INITIATION",
        target_id=initiation.id,
        after={"instance_id": instance.id},
    )
    return initiation


def get_initiation(db: Session, ctx: ScopeContext, project_id: int) -> Initiation | None:
    return db.execute(
        select(Initiation)
        .where(Initiation.project_id == project_id)
        .order_by(Initiation.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def on_initiation_approved(db: Session, instance: WorkflowInstance) -> None:
    initiation = db.get(Initiation, instance.biz_id)
    if initiation is None:
        raise BusinessRuleError("立项申请不存在")
    project = db.get(Project, initiation.project_id)
    if project is None:
        raise BusinessRuleError("项目不存在")
    initiation.status = "APPROVED"
    project.status = ProjectStatus.ACTIVE.value
    project.stage = ProjectStage.LAUNCH.value
    project.budget_amount = initiation.estimate_cost
    project.contract_amount = initiation.estimate_income
    db.flush()
    write_audit(
        db,
        user=None,
        action="INITIATION_APPROVED",
        target_type="PROJECT",
        target_id=project.id,
        company_id=project.company_id,
    )
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=[project.manager_id, initiation.applicant_id],
        title=f"立项通过：{project.name}",
        content=f"项目 {project.no} 已立项成功，请继续完善项目计划。",
        type="APPROVAL",
        biz_type="PROJECT_INITIATION",
        biz_id=initiation.id,
        link=f"/projects/{project.id}",
        email=True,
    )


def on_initiation_rejected(db: Session, instance: WorkflowInstance) -> None:
    initiation = db.get(Initiation, instance.biz_id)
    if initiation is None:
        return
    initiation.status = "REJECTED"
    project = db.get(Project, initiation.project_id)
    if project:
        project.status = ProjectStatus.DRAFT.value
    db.flush()


def on_initiation_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    initiation = db.get(Initiation, instance.biz_id)
    if initiation is None:
        return
    initiation.status = "DRAFT"
    project = db.get(Project, initiation.project_id)
    if project:
        project.status = ProjectStatus.DRAFT.value
    db.flush()


# ---------------------------------------------------------------- 阶段
def confirm_plan(db: Session, user: User, ctx: ScopeContext, project_id: int) -> Project:
    project = get_project(db, ctx, project_id)
    if project.status != ProjectStatus.ACTIVE.value:
        raise BusinessRuleError("只有已立项的进行中项目可确认计划")
    if project.stage not in {ProjectStage.LAUNCH.value, ProjectStage.PLAN.value}:
        raise BusinessRuleError("项目当前阶段不允许确认计划")
    task_count = int(
        db.execute(select(func.count(Task.id)).where(Task.project_id == project.id)).scalar_one()
    )
    if task_count == 0:
        raise BusinessRuleError("请先拆解 WBS 与任务计划")
    _snapshot_baseline(db, project.id)
    project.stage = ProjectStage.PLAN_CONFIRMED.value
    db.flush()
    write_audit(db, user=user, action="CONFIRM_PLAN", target_type="PROJECT", target_id=project.id)
    return project


def start_execution(db: Session, user: User, ctx: ScopeContext, project_id: int) -> Project:
    project = get_project(db, ctx, project_id)
    if project.stage != ProjectStage.PLAN_CONFIRMED.value:
        raise BusinessRuleError("请先确认项目计划")
    project.stage = ProjectStage.EXECUTE.value
    if not project.actual_start:
        project.actual_start = today()
    db.flush()
    write_audit(db, user=user, action="START_EXECUTION", target_type="PROJECT", target_id=project.id)
    return project


def _snapshot_baseline(db: Session, project_id: int) -> int:
    version = int(
        db.execute(
            select(func.max(TaskBaseline.baseline_version)).where(TaskBaseline.project_id == project_id)
        ).scalar_one()
        or 0
    ) + 1
    rows = db.execute(
        select(Task, WBS).outerjoin(WBS, Task.wbs_id == WBS.id).where(Task.project_id == project_id)
    ).all()
    for task, wbs in rows:
        db.add(
            TaskBaseline(
                project_id=project_id,
                task_id=task.id,
                wbs_code=wbs.code if wbs else None,
                name=task.name,
                owner_id=task.owner_id,
                plan_start=task.plan_start,
                plan_end=task.plan_end,
                estimate_hours=task.estimate_hours,
                baseline_version=version,
            )
        )
    db.flush()
    return version


def baseline_list(db: Session, ctx: ScopeContext, project_id: int, limit: int = 200) -> list[TaskBaseline]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(
            select(TaskBaseline)
            .where(TaskBaseline.project_id == project_id)
            .order_by(TaskBaseline.baseline_version.desc(), TaskBaseline.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )


def close_check(db: Session, ctx: ScopeContext, project_id: int) -> dict:
    project = get_project(db, ctx, project_id)
    blockers: list[str] = []
    unfinished = int(
        db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project.id, Task.status.notin_(["DONE", "CANCELED"])
            )
        ).scalar_one()
    )
    if unfinished:
        blockers.append(f"存在 {unfinished} 个未完成任务")
    unpaid = int(
        db.execute(
            select(func.count(Payment.id)).where(
                Payment.project_id == project.id, Payment.status == PaymentStatus.PENDING
            )
        ).scalar_one()
    )
    if unpaid:
        blockers.append(f"存在 {unpaid} 笔未结清付款")
    acceptance = db.execute(
        select(Acceptance)
        .where(Acceptance.project_id == project.id)
        .order_by(Acceptance.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if acceptance is None or acceptance.status != "APPROVED":
        blockers.append("验收申请未审批通过")
    elif not acceptance.sign_file_id:
        blockers.append("验收单未归档")
    elif not db.execute(
        select(Archive.id).where(Archive.project_id == project.id, Archive.doc_type == "ACCEPTANCE").limit(1)
    ).first():
        blockers.append("验收单未归档到项目档案")
    open_issues = int(
        db.execute(
            select(func.count(Issue.id)).where(Issue.project_id == project.id, Issue.status != "CLOSED")
        ).scalar_one()
    )
    if open_issues:
        blockers.append(f"存在 {open_issues} 个未关闭问题")
    return {"project_id": project.id, "blockers": blockers, "can_close": not blockers}


def close_project(
    db: Session, user: User, ctx: ScopeContext, project_id: int, *, force: bool = False, reason: str | None = None
) -> Project:
    project = get_project(db, ctx, project_id)
    if project.status in {ProjectStatus.CLOSED.value, ProjectStatus.ARCHIVED.value}:
        raise BusinessRuleError("项目已关闭")
    if force:
        if not reason or len(reason.strip()) < 5:
            raise BusinessRuleError("强制关闭必须填写不少于 5 个字的关闭原因")
        if not user.is_super and "project:force-close" not in ctx.permissions:
            raise BusinessRuleError("缺少强制关闭项目权限")
    else:
        check = close_check(db, ctx, project_id)
        if check["blockers"]:
            raise BusinessRuleError("项目关闭校验未通过：" + "；".join(check["blockers"]))
    project.stage = ProjectStage.CLOSE.value
    project.status = ProjectStatus.CLOSED.value
    project.closed_at = now()
    project.close_reason = (reason or "正常关闭")[:500]
    project.version = int(project.version or 1) + 1
    db.flush()
    from app.services.report.pnl import generate_project_pnl

    generate_project_pnl(db, project, period=now().strftime("%Y-%m"), persist=True)
    write_audit(
        db,
        user=user,
        action="FORCE_CLOSE_PROJECT" if force else "CLOSE_PROJECT",
        target_type="PROJECT",
        target_id=project.id,
        after={"reason": project.close_reason},
    )
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=[project.manager_id],
        title=f"项目已关闭：{project.name}",
        content=f"项目 {project.no} 已关闭，关闭原因：{project.close_reason}",
        type="SYSTEM",
        biz_type="PROJECT",
        biz_id=project.id,
        link=f"/projects/{project.id}",
        email=False,
    )
    return project


def archive_project(db: Session, user: User, ctx: ScopeContext, project_id: int) -> Project:
    project = get_project(db, ctx, project_id)
    if project.status != ProjectStatus.CLOSED.value:
        raise BusinessRuleError("仅已关闭项目可归档")
    archived = int(
        db.execute(select(func.count(Archive.id)).where(Archive.project_id == project.id)).scalar_one()
    )
    if archived == 0:
        raise BusinessRuleError("请先上传归档资料")
    project.stage = ProjectStage.ARCHIVED.value
    project.status = "ARCHIVED"
    db.flush()
    write_audit(db, user=user, action="ARCHIVE_PROJECT", target_type="PROJECT", target_id=project.id)
    return project


def add_archive(
    db: Session, user: User, ctx: ScopeContext, project_id: int, doc_type: str, file_id: int | None
) -> Archive:
    project = get_project(db, ctx, project_id)
    if not doc_type:
        raise BusinessRuleError("请填写归档资料类型")
    item = Archive(
        company_id=project.company_id,
        project_id=project.id,
        doc_type=doc_type[:64],
        file_id=file_id,
        archived_by=user.id,
    )
    db.add(item)
    db.flush()
    write_audit(
        db,
        user=user,
        action="ARCHIVE_DOCUMENT",
        target_type="PROJECT",
        target_id=project.id,
        after={"doc_type": doc_type, "file_id": file_id},
    )
    return item


def list_archives(db: Session, ctx: ScopeContext, project_id: int) -> list[Archive]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(select(Archive).where(Archive.project_id == project_id).order_by(Archive.id.desc()))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------- 成员
def list_members(db: Session, ctx: ScopeContext, project_id: int) -> list[ProjectMember]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(select(ProjectMember).where(ProjectMember.project_id == project_id).order_by(ProjectMember.id))
        .scalars()
        .all()
    )


def add_member(
    db: Session, user: User, ctx: ScopeContext, project_id: int, target_user_id: int, role: str = "MEMBER"
) -> ProjectMember:
    project = get_project(db, ctx, project_id)
    target = _check_user(db, target_user_id, project.company_id)
    if target is None:
        raise BusinessRuleError("成员不存在")
    if role not in {"PM", "MEMBER", "OBSERVER"}:
        raise BusinessRuleError("成员角色非法")
    exists = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == target.id
        )
    ).scalar_one_or_none()
    if exists:
        raise BusinessRuleError("该成员已在项目中")
    member = ProjectMember(
        company_id=project.company_id,
        project_id=project.id,
        user_id=target.id,
        role=role,
        join_at=today(),
    )
    db.add(member)
    db.flush()
    write_audit(
        db,
        user=user,
        action="ADD_PROJECT_MEMBER",
        target_type="PROJECT",
        target_id=project.id,
        after={"user_id": target.id, "role": role},
    )
    return member


def remove_member(db: Session, user: User, ctx: ScopeContext, project_id: int, member_id: int) -> None:
    project = get_project(db, ctx, project_id)
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != project.id:
        raise NotFoundError("项目成员不存在")
    if member.user_id == project.manager_id:
        raise BusinessRuleError("不能移除项目经理")
    db.delete(member)
    db.flush()
    write_audit(
        db,
        user=user,
        action="REMOVE_PROJECT_MEMBER",
        target_type="PROJECT",
        target_id=project.id,
        before={"user_id": member.user_id},
    )


def project_deviation(db: Session, ctx: ScopeContext, project_id: int) -> dict:
    project = get_project(db, ctx, project_id)
    tasks = list(db.execute(select(Task).where(Task.project_id == project.id)).scalars().all())
    total = len(tasks)
    done = sum(1 for task in tasks if task.status == "DONE")
    delayed = sum(
        1
        for task in tasks
        if task.plan_end and task.plan_end < today() and task.status not in {"DONE", "CANCELED"}
    )
    # 偏差只对照最新基线版本，避免多轮基线变更被重复累加。
    latest_version = db.execute(
        select(func.max(TaskBaseline.baseline_version)).where(TaskBaseline.project_id == project.id)
    ).scalar_one_or_none()
    baseline: list[TaskBaseline] = []
    if latest_version:
        baseline = list(
            db.execute(
                select(TaskBaseline)
                .where(
                    TaskBaseline.project_id == project.id,
                    TaskBaseline.baseline_version == latest_version,
                )
                .order_by(TaskBaseline.id)
            )
            .scalars()
            .all()
        )
    baseline_count = len(baseline)
    planned_hours = sum((Decimal(str(item.estimate_hours or 0)) for item in baseline), Decimal("0"))
    actual_hours = sum((Decimal(str(task.actual_hours or 0)) for task in tasks), Decimal("0"))
    from app.services.cost.cost import project_actual_cost

    actual_cost = project_actual_cost(db, project.id)
    budget = Decimal(str(project.budget_amount or 0))
    return {
        "task_total": total,
        "task_done": done,
        "task_delayed": delayed,
        "completion_rate": round(done / total, 4) if total else 0.0,
        "baseline_version": int(latest_version or 0),
        "baseline_tasks": baseline_count,
        "planned_hours": planned_hours,
        "actual_hours": actual_hours,
        "schedule_variance": done - total,
        "cost_variance": budget - actual_cost if actual_cost else budget,
    }
