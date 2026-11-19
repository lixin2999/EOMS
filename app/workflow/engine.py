from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import LockBusyError, cache
from app.core.config import settings
from app.core.errors import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.enums import WorkflowAction, WorkflowStatus, WorkflowTaskStatus
from app.models.iam import Dept, Role, User
from app.models.project import Project, ProjectMember
from app.models.workflow import WorkflowCc, WorkflowDefinition, WorkflowInstance, WorkflowRecord, WorkflowTask
from app.services.iam.audit import write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now
from app.workflow.callbacks import dispatch
from app.workflow.definitions import validate_definition

logger = get_logger("eoms.workflow")


# ---------------------------------------------------------------- 流程定义
def get_definition(db: Session, company_id: int, code: str, def_id: int | None = None) -> WorkflowDefinition:
    if def_id:
        definition = db.get(WorkflowDefinition, def_id)
        if definition is None or definition.company_id != company_id:
            raise NotFoundError("流程定义不存在")
        return definition
    definition = db.execute(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.company_id == company_id,
            WorkflowDefinition.code == code,
            WorkflowDefinition.enabled.is_(True),
        )
        .order_by(WorkflowDefinition.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if definition is None:
        raise BusinessRuleError(f"未配置启用的审批流程：{code}")
    validate_definition(definition.nodes_json)
    return definition


def save_definition(
    db: Session,
    *,
    user: User,
    code: str,
    name: str,
    nodes_json: dict[str, Any],
    enabled: bool = True,
    remark: str | None = None,
) -> WorkflowDefinition:
    validate_definition(nodes_json)
    max_version = (
        db.execute(
            select(func.max(WorkflowDefinition.version)).where(
                WorkflowDefinition.company_id == user.company_id, WorkflowDefinition.code == code
            )
        ).scalar_one()
        or 0
    )
    definition = WorkflowDefinition(
        company_id=user.company_id,
        code=code,
        name=name,
        version=int(max_version) + 1,
        nodes_json=nodes_json,
        enabled=enabled,
        remark=remark,
    )
    if enabled:
        db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.company_id == user.company_id, WorkflowDefinition.code == code
            )
        )
        # 同 code 仅保留一个启用版本
        old = db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.company_id == user.company_id,
                WorkflowDefinition.code == code,
                WorkflowDefinition.enabled.is_(True),
            )
        ).scalars()
        for item in old:
            item.enabled = False
    db.add(definition)
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_WORKFLOW_DEFINITION",
        target_type="WORKFLOW_DEFINITION",
        target_id=definition.id,
        after={"code": code, "version": definition.version},
    )
    return definition


# ---------------------------------------------------------------- 启动流程
def start_workflow(
    db: Session,
    *,
    company_id: int,
    dept_id: int | None,
    project_id: int | None,
    initiator: User,
    def_code: str,
    biz_type: str,
    biz_id: int,
    title: str,
    context: dict[str, Any],
    version: int = 1,
) -> WorkflowInstance:
    definition = get_definition(db, company_id, def_code)
    instance = WorkflowInstance(
        company_id=company_id,
        dept_id=dept_id,
        project_id=project_id,
        creator_id=initiator.id,
        def_id=definition.id,
        def_code=definition.code,
        biz_type=biz_type,
        biz_id=biz_id,
        title=title[:255],
        initiator_id=initiator.id,
        current_node="START",
        status=WorkflowStatus.RUNNING.value,
        context_json={**context, "initiator_name": initiator.real_name},
        version=version,
    )
    db.add(instance)
    db.flush()
    _add_record(
        db,
        instance,
        node_code="START",
        node_name="发起人提交",
        operator=initiator,
        action=WorkflowAction.SUBMIT.value,
        comment="提交审批",
    )
    _advance(db, instance, definition, "START")
    return instance


def _add_record(
    db: Session,
    instance: WorkflowInstance,
    *,
    node_code: str,
    node_name: str | None,
    operator: User | None,
    action: str,
    comment: str | None = None,
    attachments: list[int] | None = None,
    operator_id: int | None = None,
    operator_name: str | None = None,
) -> WorkflowRecord:
    record = WorkflowRecord(
        company_id=instance.company_id,
        instance_id=instance.id,
        node_code=node_code,
        node_name=node_name,
        operator_id=operator.id if operator else (operator_id or instance.initiator_id),
        operator_name=operator.real_name if operator else (operator_name or "系统"),
        action=action,
        comment=comment,
        attachments=attachments or [],
    )
    db.add(record)
    db.flush()
    return record


# ---------------------------------------------------------------- 条件路由
def _condition_ok(condition: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    if not condition:
        return True
    amount = Decimal(str(context.get("amount") or 0))
    days = Decimal(str(context.get("days") or 0))
    secret = str(context.get("secret_level") or "INTERNAL")
    category = str(context.get("category") or "")
    biz_kind = str(context.get("type") or "")

    if "min_amount" in condition and amount < Decimal(str(condition["min_amount"])):
        return False
    if "max_amount" in condition and amount > Decimal(str(condition["max_amount"])):
        return False
    if "min_days" in condition and days < Decimal(str(condition["min_days"])):
        return False
    if "secret_levels" in condition and secret not in set(condition["secret_levels"]):
        return False
    if "categories" in condition and category not in set(condition["categories"]):
        return False
    return "types" not in condition or biz_kind in set(condition["types"])


# ---------------------------------------------------------------- 审批人解析
def _active_users(db: Session, company_id: int) -> list[User]:
    return list(
        db.execute(select(User).where(User.company_id == company_id, User.status == "ACTIVE")).scalars().all()
    )


def _users_with_role(db: Session, company_id: int, role_code: str) -> list[User]:
    role = db.execute(
        select(Role).where(Role.code == role_code, Role.status == "ACTIVE").order_by(Role.company_id.is_(None))
    ).scalars().first()
    if role is None:
        return []
    return [user for user in _active_users(db, company_id) if role.id in (user.role_ids or [])]


def _dept_chain(db: Session, dept_id: int | None) -> list[Dept]:
    chain: list[Dept] = []
    seen: set[int] = set()
    current = db.get(Dept, dept_id) if dept_id else None
    while current is not None and current.id not in seen:
        chain.append(current)
        seen.add(current.id)
        current = db.get(Dept, current.parent_id) if current.parent_id else None
    return chain


def _dept_leaders(db: Session, dept_id: int | None) -> list[User]:
    result: list[User] = []
    for dept in _dept_chain(db, dept_id):
        if dept.leader_user_id:
            leader = db.get(User, dept.leader_user_id)
            if leader and leader.status == "ACTIVE" and leader.company_id == dept.company_id:
                result.append(leader)
    return result


def _resolve_assignees(
    db: Session,
    instance: WorkflowInstance,
    spec: dict[str, Any],
) -> list[User]:
    kind = (spec or {}).get("type")
    initiator = db.get(User, instance.initiator_id)
    company_id = instance.company_id
    users: list[User] = []
    if kind == "USER":
        user = db.get(User, int(spec.get("value") or 0))
        if user and user.company_id == company_id and user.status == "ACTIVE":
            users = [user]
    elif kind == "ROLE":
        users = _users_with_role(db, company_id, str(spec.get("value")))
    elif kind in {"DEPT_LEADER", "SUPERIOR"}:
        users = _dept_leaders(db, instance.dept_id or (initiator.dept_id if initiator else None))
    elif kind == "DEPT_MANAGER":
        leaders = _dept_leaders(db, instance.dept_id or (initiator.dept_id if initiator else None))
        users = _users_with_role(db, company_id, "MANAGER")
        users = leaders + users
    elif kind == "PM":
        if instance.project_id:
            project = db.get(Project, instance.project_id)
            if project:
                manager = db.get(User, project.manager_id)
                if manager and manager.status == "ACTIVE":
                    users = [manager]
                else:
                    member_ids = db.execute(
                        select(ProjectMember.user_id).where(
                            ProjectMember.project_id == project.id, ProjectMember.role == "PM"
                        )
                    ).scalars()
                    users = [
                        user
                        for user in _active_users(db, company_id)
                        if user.id in set(member_ids)
                    ]
    elif kind == "CREATOR" and initiator:
        users = [initiator]
    return _dedupe_users(users)


def _dedupe_users(users: list[User]) -> list[User]:
    seen: set[int] = set()
    result: list[User] = []
    for user in users:
        if user.id in seen:
            continue
        seen.add(user.id)
        result.append(user)
    return result


def _fallback_approvers(db: Session, instance: WorkflowInstance) -> list[User]:
    """节点审批人缺失时逐级兜底，避免流程卡死。"""
    initiator = db.get(User, instance.initiator_id)
    candidates = _dept_leaders(db, instance.dept_id or (initiator.dept_id if initiator else None))
    candidates += _users_with_role(db, instance.company_id, "MANAGER")
    candidates += _users_with_role(db, instance.company_id, "DIRECTOR")
    admins = list(
        db.execute(
            select(User).where(
                User.company_id == instance.company_id, User.is_super.is_(True), User.status == "ACTIVE"
            )
        )
        .scalars()
        .all()
    )
    candidates += admins
    return [user for user in _dedupe_users(candidates) if user.id != instance.initiator_id]


def _skip_task(
    db: Session,
    instance: WorkflowInstance,
    node: dict[str, Any],
    reason: str,
) -> None:
    initiator = db.get(User, instance.initiator_id)
    task = WorkflowTask(
        company_id=instance.company_id,
        dept_id=instance.dept_id,
        project_id=instance.project_id,
        creator_id=instance.initiator_id,
        instance_id=instance.id,
        node_code=str(node["code"]),
        node_name=str(node.get("name") or node["code"]),
        assignee_id=instance.initiator_id,
        candidate_ids=[],
        status=WorkflowTaskStatus.SKIPPED.value,
        action="SKIP",
        comment=reason,
        mode="ANY",
        arrive_at=now(),
        finish_at=now(),
        due_at=None,
    )
    db.add(task)
    _add_record(
        db,
        instance,
        node_code=str(node["code"]),
        node_name=node.get("name"),
        operator=initiator,
        action="SKIP",
        comment=reason,
        operator_name="系统",
    )
    db.flush()


def _advance(db: Session, instance: WorkflowInstance, definition: WorkflowDefinition, from_code: str) -> None:
    nodes = definition.nodes_json.get("nodes", [])
    codes = [str(node.get("code")) for node in nodes]
    if from_code not in codes:
        raise BusinessRuleError(f"流程节点不存在：{from_code}")
    start_index = codes.index(from_code)
    settings_json = definition.nodes_json.get("settings") or {}
    node_due_hours = int(settings_json.get("due_hours") or settings.workflow_due_hours)

    for node in nodes[start_index + 1 :]:
        node_type = node.get("type")
        if node_type == "END":
            _finish_approved(db, instance)
            return
        if node_type != "APPROVAL":
            continue
        if not _condition_ok(node.get("condition"), instance.context_json):
            _skip_task(db, instance, node, "条件不满足，自动跳过")
            continue
        assignees = _resolve_assignees(db, instance, node.get("assignee") or {})
        assignees = [user for user in assignees if user.id != instance.initiator_id]
        if not assignees:
            assignees = _fallback_approvers(db, instance)
        if not assignees:
            raise BusinessRuleError(f"节点「{node.get('name')}」未找到可用审批人，请联系管理员")
        mode = str(node.get("mode") or "ANY").upper()
        instance.current_node = str(node["code"])
        instance.status = WorkflowStatus.RUNNING.value
        due_at = now() + timedelta(hours=node_due_hours)
        for assignee in assignees:
            db.add(
                WorkflowTask(
                    company_id=instance.company_id,
                    dept_id=instance.dept_id,
                    project_id=instance.project_id,
                    creator_id=instance.initiator_id,
                    instance_id=instance.id,
                    node_code=str(node["code"]),
                    node_name=str(node.get("name") or node["code"]),
                    assignee_id=assignee.id,
                    candidate_ids=[user.id for user in assignees],
                    status=WorkflowTaskStatus.PENDING.value,
                    mode=mode,
                    arrive_at=now(),
                    due_at=due_at,
                    seq=1,
                )
            )
        db.flush()
        notify_with_email(
            db,
            company_id=instance.company_id,
            user_ids=[user.id for user in assignees],
            title=f"待审批：{instance.title}",
            content=(
                f"{instance.context_json.get('initiator_name', '')} "
                f"发起的审批已到达「{node.get('name')}」，请及时处理。"
            ),
            type="APPROVAL",
            biz_type=instance.biz_type,
            biz_id=instance.biz_id,
            link=f"/workflow/tasks?instance_id={instance.id}",
        )
        return

    _finish_approved(db, instance)


def _finish_approved(db: Session, instance: WorkflowInstance) -> None:
    instance.status = WorkflowStatus.APPROVED.value
    instance.current_node = "END"
    instance.finish_at = now()
    instance.version = int(instance.version or 1) + 1
    _add_record(
        db,
        instance,
        node_code="END",
        node_name="归档",
        operator=None,
        action="APPROVED",
        comment="流程审批通过",
        operator_name="系统",
        operator_id=instance.initiator_id,
    )
    db.flush()
    dispatch(db, "approved", instance)
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=[instance.initiator_id],
        title=f"审批通过：{instance.title}",
        content="您的审批已全部通过。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/instances/{instance.id}",
        email=False,
    )
    db.flush()


def _finish_rejected(db: Session, instance: WorkflowInstance) -> None:
    instance.status = WorkflowStatus.REJECTED.value
    instance.finish_at = now()
    instance.version = int(instance.version or 1) + 1
    db.flush()
    dispatch(db, "rejected", instance)
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=[instance.initiator_id],
        title=f"审批驳回：{instance.title}",
        content="您的审批被驳回，请修改后重新提交。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/instances/{instance.id}",
        email=False,
    )
    db.flush()


# ---------------------------------------------------------------- 审批动作
def _get_instance_for_update(db: Session, instance_id: int, company_id: int) -> WorkflowInstance:
    instance = db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
    ).scalar_one_or_none()
    if instance is None or instance.company_id != company_id:
        raise NotFoundError("流程实例不存在")
    return instance


def _get_task(
    db: Session,
    instance: WorkflowInstance,
    user: User,
    task_id: int | None,
) -> WorkflowTask:
    stmt = select(WorkflowTask).where(
        WorkflowTask.instance_id == instance.id,
        WorkflowTask.assignee_id == user.id,
        WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
    )
    if task_id:
        stmt = stmt.where(WorkflowTask.id == task_id)
    else:
        stmt = stmt.where(WorkflowTask.node_code == (instance.current_node or ""))
    task = db.execute(stmt.order_by(WorkflowTask.id).with_for_update()).scalars().first()
    if task is None:
        raise ForbiddenError("您没有该节点的待办任务")
    return task


def act(
    db: Session,
    *,
    user: User,
    instance_id: int,
    action: str,
    task_id: int | None = None,
    comment: str | None = None,
    target_user_id: int | None = None,
    target_user_ids: list[int] | None = None,
    back_to: str = "INITIATOR",
    mode: str = "ANY",
    cc_user_ids: list[int] | None = None,
    attachments: list[int] | None = None,
) -> WorkflowInstance:
    action = action.upper()
    if action not in {item.value for item in WorkflowAction}:
        raise BusinessRuleError("不支持的审批动作")
    try:
        with cache.lock(f"wf:{instance_id}"):
            instance = _get_instance_for_update(db, instance_id, user.company_id)
            if instance.status != WorkflowStatus.RUNNING.value:
                raise ConflictError("流程已结束，不能重复操作")
            definition = db.get(WorkflowDefinition, instance.def_id)
            if definition is None:
                raise BusinessRuleError("流程定义不存在")

            if action == WorkflowAction.WITHDRAW.value:
                _withdraw(db, instance, user)
            elif action == WorkflowAction.URGE.value:
                _urge(db, instance, user)
            elif action == WorkflowAction.CC.value:
                _cc(db, instance, user, cc_user_ids or [])
            else:
                task = _get_task(db, instance, user, task_id)
                if action == WorkflowAction.APPROVE.value:
                    _approve(db, instance, definition, task, user, comment, attachments)
                elif action == WorkflowAction.REJECT.value:
                    _reject(db, instance, definition, task, user, comment, back_to)
                elif action == WorkflowAction.TRANSFER.value:
                    _transfer(db, instance, task, user, target_user_id, comment)
                elif action == WorkflowAction.ADD_SIGN.value:
                    _add_sign(db, instance, task, user, target_user_ids or [], mode, comment)
            db.flush()
            return instance
    except LockBusyError:
        raise ConflictError("该流程正在被处理，请稍后刷新重试") from None


def _complete_task(
    db: Session,
    task: WorkflowTask,
    *,
    status: str,
    action: str,
    comment: str | None,
) -> None:
    task.status = status
    task.action = action
    task.comment = (comment or "")[:1000] or None
    task.finish_at = now()
    task.version = int(task.version or 1) + 1
    db.flush()


def _skip_pending_at_node(
    db: Session, instance: WorkflowInstance, node_code: str, exclude_id: int | None = None
) -> None:
    rows = db.execute(
        select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.node_code == node_code,
            WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
        )
    ).scalars()
    for row in rows:
        if exclude_id and row.id == exclude_id:
            continue
        row.status = WorkflowTaskStatus.SKIPPED.value
        row.action = "SKIP"
        row.comment = "同节点其他审批人已处理"
        row.finish_at = now()
    db.flush()


def _approve(
    db: Session,
    instance: WorkflowInstance,
    definition: WorkflowDefinition,
    task: WorkflowTask,
    user: User,
    comment: str | None,
    attachments: list[int] | None,
) -> None:
    _complete_task(db, task, status=WorkflowTaskStatus.APPROVED.value, action="APPROVE", comment=comment)
    _add_record(
        db,
        instance,
        node_code=task.node_code,
        node_name=task.node_name,
        operator=user,
        action=WorkflowAction.APPROVE.value,
        comment=comment,
        attachments=attachments,
    )
    if task.mode == "ALL":
        pending = db.execute(
            select(func.count(WorkflowTask.id)).where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.node_code == task.node_code,
                WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
            )
        ).scalar_one()
        if int(pending) > 0:
            notify_with_email(
                db,
                company_id=instance.company_id,
                user_ids=[instance.initiator_id],
                title=f"会签进度：{instance.title}",
                content=f"{user.real_name} 已同意，等待其他会签人处理。",
                type="APPROVAL",
                biz_type=instance.biz_type,
                biz_id=instance.biz_id,
                link=f"/workflow/instances/{instance.id}",
                email=False,
            )
            return
    else:
        _skip_pending_at_node(db, instance, task.node_code, exclude_id=task.id)
    _advance(db, instance, definition, task.node_code)


def _reject(
    db: Session,
    instance: WorkflowInstance,
    definition: WorkflowDefinition,
    task: WorkflowTask,
    user: User,
    comment: str | None,
    back_to: str,
) -> None:
    if not comment or len(comment.strip()) < 2:
        raise BusinessRuleError("驳回时必须填写驳回原因")
    _complete_task(db, task, status=WorkflowTaskStatus.REJECTED.value, action="REJECT", comment=comment)
    _skip_pending_at_node(db, instance, task.node_code, exclude_id=task.id)
    _add_record(
        db,
        instance,
        node_code=task.node_code,
        node_name=task.node_name,
        operator=user,
        action=WorkflowAction.REJECT.value,
        comment=comment,
    )
    target = (back_to or "INITIATOR").upper()
    if target == "PREVIOUS":
        nodes = definition.nodes_json.get("nodes", [])
        codes = [str(node.get("code")) for node in nodes]
        current_index = codes.index(task.node_code) if task.node_code in codes else -1
        previous: dict[str, Any] | None = None
        for node in reversed(nodes[:current_index]):
            if node.get("type") == "APPROVAL" and _condition_ok(node.get("condition"), instance.context_json):
                previous = node
                break
        if previous is not None:
            assignees = [
                item
                for item in _resolve_assignees(db, instance, previous.get("assignee") or {})
                if item.id != instance.initiator_id
            ] or _fallback_approvers(db, instance)
            if assignees:
                instance.current_node = str(previous["code"])
                instance.status = WorkflowStatus.RUNNING.value
                due_at = now() + timedelta(hours=settings.workflow_due_hours)
                for assignee in assignees:
                    db.add(
                        WorkflowTask(
                            company_id=instance.company_id,
                            dept_id=instance.dept_id,
                            project_id=instance.project_id,
                            creator_id=instance.initiator_id,
                            instance_id=instance.id,
                            node_code=str(previous["code"]),
                            node_name=str(previous.get("name") or previous["code"]),
                            assignee_id=assignee.id,
                            candidate_ids=[item.id for item in assignees],
                            status=WorkflowTaskStatus.PENDING.value,
                            mode=str(previous.get("mode") or "ANY"),
                            arrive_at=now(),
                            due_at=due_at,
                            seq=1,
                        )
                    )
                _add_record(
                    db,
                    instance,
                    node_code=str(previous["code"]),
                    node_name=previous.get("name"),
                    operator=user,
                    action="RETURN",
                    comment=f"驳回并退回至「{previous.get('name')}」",
                )
                notify_with_email(
                    db,
                    company_id=instance.company_id,
                    user_ids=[item.id for item in assignees],
                    title=f"退回重审：{instance.title}",
                    content=f"{user.real_name} 驳回并退回至「{previous.get('name')}」，请重新审核。",
                    type="APPROVAL",
                    biz_type=instance.biz_type,
                    biz_id=instance.biz_id,
                    link=f"/workflow/tasks?instance_id={instance.id}",
                )
                return
    _finish_rejected(db, instance)
    write_audit(
        db,
        user=user,
        action="WORKFLOW_REJECT",
        target_type="WORKFLOW_INSTANCE",
        target_id=instance.id,
        after={"comment": comment, "back_to": target},
    )


def _transfer(
    db: Session,
    instance: WorkflowInstance,
    task: WorkflowTask,
    user: User,
    target_user_id: int | None,
    comment: str | None,
) -> None:
    if not target_user_id:
        raise BusinessRuleError("请选择转办接收人")
    if target_user_id == user.id:
        raise BusinessRuleError("不能转办给自己")
    if target_user_id == instance.initiator_id:
        raise BusinessRuleError("不能转办给流程发起人")
    target = db.get(User, target_user_id)
    if target is None or target.company_id != instance.company_id or target.status != "ACTIVE":
        raise BusinessRuleError("转办接收人不存在或已停用")
    _complete_task(db, task, status=WorkflowTaskStatus.TRANSFERRED.value, action="TRANSFER", comment=comment)
    db.add(
        WorkflowTask(
            company_id=instance.company_id,
            dept_id=instance.dept_id,
            project_id=instance.project_id,
            creator_id=instance.initiator_id,
            instance_id=instance.id,
            node_code=task.node_code,
            node_name=task.node_name,
            assignee_id=target.id,
            candidate_ids=[target.id],
            status=WorkflowTaskStatus.PENDING.value,
            mode=task.mode,
            arrive_at=now(),
            due_at=task.due_at,
            seq=int(task.seq or 1) + 1,
        )
    )
    _add_record(
        db,
        instance,
        node_code=task.node_code,
        node_name=task.node_name,
        operator=user,
        action=WorkflowAction.TRANSFER.value,
        comment=f"转办给 {target.real_name}。{comment or ''}".strip(),
    )
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=[target.id],
        title=f"转办待审批：{instance.title}",
        content=f"{user.real_name} 将审批转办给您，请及时处理。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/tasks?instance_id={instance.id}",
    )
    write_audit(
        db,
        user=user,
        action="WORKFLOW_TRANSFER",
        target_type="WORKFLOW_TASK",
        target_id=task.id,
        after={"target_user_id": target.id},
    )


def _add_sign(
    db: Session,
    instance: WorkflowInstance,
    task: WorkflowTask,
    user: User,
    target_user_ids: list[int],
    mode: str,
    comment: str | None,
) -> None:
    targets = [uid for uid in dict.fromkeys(target_user_ids) if uid]
    if not targets:
        raise BusinessRuleError("请选择加签人")
    if user.id in targets:
        raise BusinessRuleError("不能给自己加签")
    if instance.initiator_id in targets:
        raise BusinessRuleError("不能给流程发起人加签")
    users = list(
        db.execute(
            select(User).where(
                User.id.in_(targets), User.company_id == instance.company_id, User.status == "ACTIVE"
            )
        )
        .scalars()
        .all()
    )
    if len(users) != len(targets):
        raise BusinessRuleError("加签人不存在或已停用")
    mode = "ALL" if mode.upper() == "ALL" else "ANY"
    pending = db.execute(
        select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.node_code == task.node_code,
            WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
        )
    ).scalars()
    for row in pending:
        row.mode = mode
    for target in users:
        db.add(
            WorkflowTask(
                company_id=instance.company_id,
                dept_id=instance.dept_id,
                project_id=instance.project_id,
                creator_id=instance.initiator_id,
                instance_id=instance.id,
                node_code=task.node_code,
                node_name=task.node_name,
                assignee_id=target.id,
                candidate_ids=[target.id],
                status=WorkflowTaskStatus.PENDING.value,
                mode=mode,
                arrive_at=now(),
                due_at=task.due_at,
                seq=int(task.seq or 1) + 1,
            )
        )
    _add_record(
        db,
        instance,
        node_code=task.node_code,
        node_name=task.node_name,
        operator=user,
        action=WorkflowAction.ADD_SIGN.value,
        comment=(
            f"{'会签' if mode == 'ALL' else '加签'}："
            f"{'、'.join(user.real_name for user in users)}。{comment or ''}"
        ).strip(),
    )
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=[target.id for target in users],
        title=f"加签待审批：{instance.title}",
        content=f"{user.real_name} 邀请您参与审批，请及时处理。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/tasks?instance_id={instance.id}",
    )


def _withdraw(db: Session, instance: WorkflowInstance, user: User) -> None:
    if user.id != instance.initiator_id and not user.is_super:
        raise ForbiddenError("只有发起人可以撤回流程")
    acted = db.execute(
        select(func.count(WorkflowTask.id)).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.status.in_(
                [
                    WorkflowTaskStatus.APPROVED.value,
                    WorkflowTaskStatus.REJECTED.value,
                    WorkflowTaskStatus.TRANSFERRED.value,
                ]
            ),
        )
    ).scalar_one()
    if int(acted) > 0:
        raise BusinessRuleError("流程已被处理，不能撤回")
    definition = db.get(WorkflowDefinition, instance.def_id)
    allow = bool(((definition.nodes_json if definition else {}).get("settings") or {}).get("allow_withdraw", True))
    if not allow:
        raise BusinessRuleError("该流程不允许撤回")
    rows = db.execute(
        select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
        )
    ).scalars()
    for row in rows:
        row.status = WorkflowTaskStatus.SKIPPED.value
        row.action = "WITHDRAW"
        row.comment = "发起人撤回"
        row.finish_at = now()
    instance.status = WorkflowStatus.CANCELED.value
    instance.finish_at = now()
    instance.current_node = "START"
    instance.version = int(instance.version or 1) + 1
    _add_record(
        db,
        instance,
        node_code="START",
        node_name="发起人提交",
        operator=user,
        action=WorkflowAction.WITHDRAW.value,
        comment="发起人撤回流程",
    )
    db.flush()
    dispatch(db, "withdrawn", instance)
    write_audit(
        db,
        user=user,
        action="WORKFLOW_WITHDRAW",
        target_type="WORKFLOW_INSTANCE",
        target_id=instance.id,
    )


def _urge(db: Session, instance: WorkflowInstance, user: User) -> None:
    if user.id != instance.initiator_id and not user.is_super:
        pending_self = db.execute(
            select(func.count(WorkflowTask.id)).where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.assignee_id == user.id,
                WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
            )
        ).scalar_one()
        if int(pending_self) == 0:
            raise ForbiddenError("无权催办该流程")
    tasks = db.execute(
        select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
        )
    ).scalars()
    assignees = [task.assignee_id for task in tasks]
    if not assignees:
        raise BusinessRuleError("当前没有待办的审批人")
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=assignees,
        title=f"审批催办：{instance.title}",
        content=f"{user.real_name} 催办该审批，请尽快处理。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/tasks?instance_id={instance.id}",
        email=False,
    )
    _add_record(
        db,
        instance,
        node_code=instance.current_node or "",
        node_name="催办",
        operator=user,
        action=WorkflowAction.URGE.value,
        comment="发起催办",
    )


def _cc(db: Session, instance: WorkflowInstance, user: User, cc_user_ids: list[int]) -> None:
    targets = [uid for uid in dict.fromkeys(cc_user_ids) if uid]
    if not targets:
        raise BusinessRuleError("请选择抄送人")
    users = list(
        db.execute(
            select(User).where(
                User.id.in_(targets), User.company_id == instance.company_id, User.status == "ACTIVE"
            )
        )
        .scalars()
        .all()
    )
    if len(users) != len(targets):
        raise BusinessRuleError("抄送人不存在或已停用")
    existing = set(
        db.execute(
            select(WorkflowCc.user_id).where(
                WorkflowCc.instance_id == instance.id, WorkflowCc.user_id.in_(targets)
            )
        ).scalars()
    )
    for target in users:
        if target.id not in existing:
            db.add(WorkflowCc(company_id=instance.company_id, instance_id=instance.id, user_id=target.id))
    notify_with_email(
        db,
        company_id=instance.company_id,
        user_ids=[target.id for target in users if target.id not in existing],
        title=f"抄送：{instance.title}",
        content=f"{user.real_name} 抄送该审批给您。",
        type="APPROVAL",
        biz_type=instance.biz_type,
        biz_id=instance.biz_id,
        link=f"/workflow/instances/{instance.id}",
        email=False,
    )
    _add_record(
        db,
        instance,
        node_code=instance.current_node or "",
        node_name="抄送",
        operator=user,
        action=WorkflowAction.CC.value,
        comment=f"抄送给：{'、'.join(target.real_name for target in users)}",
    )


# ---------------------------------------------------------------- 超时催办
def overdue_tasks(db: Session, limit: int = 200) -> int:
    rows = (
        db.execute(
            select(WorkflowTask)
            .where(
                WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
                WorkflowTask.due_at.is_not(None),
                WorkflowTask.due_at < now(),
                WorkflowTask.reminded_at.is_(None),
            )
            .order_by(WorkflowTask.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for task in rows:
        instance = db.get(WorkflowInstance, task.instance_id)
        if instance is None or instance.status != WorkflowStatus.RUNNING.value:
            task.reminded_at = now()
            continue
        notify_with_email(
            db,
            company_id=instance.company_id,
            user_ids=[task.assignee_id],
            title=f"审批超时提醒：{instance.title}",
            content=f"该审批在「{task.node_name}」节点已超时，请尽快处理。",
            type="ALERT",
            biz_type=instance.biz_type,
            biz_id=instance.biz_id,
            link=f"/workflow/tasks?instance_id={instance.id}",
            email=False,
        )
        task.reminded_at = now()
    db.flush()
    return len(rows)
