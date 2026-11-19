"""流程查询与审批动作编排（API 层薄封装）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.iam import User
from app.models.workflow import WorkflowCc, WorkflowDefinition, WorkflowInstance, WorkflowRecord, WorkflowTask
from app.workflow import engine


def list_instances(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str | None = None,
    biz_type: str | None = None,
    keyword: str | None = None,
    mine: bool = False,
) -> dict:
    stmt = select(WorkflowInstance)
    condition = scope_condition(ctx, WorkflowInstance)
    if condition is not None:
        stmt = stmt.where(condition)
    if mine:
        stmt = stmt.where(WorkflowInstance.initiator_id == ctx.user_id)
    if status:
        stmt = stmt.where(WorkflowInstance.status == status)
    if biz_type:
        stmt = stmt.where(WorkflowInstance.biz_type == biz_type)
    if keyword:
        stmt = stmt.where(
            or_(
                WorkflowInstance.title.like(f"%{keyword}%"),
                WorkflowInstance.biz_type.like(f"%{keyword}%"),
            )
        )
    stmt = stmt.order_by(WorkflowInstance.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def list_tasks(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str = "PENDING",
    mine: bool = True,
    biz_type: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = select(WorkflowTask, WorkflowInstance).join(
        WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id
    )
    if mine:
        stmt = stmt.where(WorkflowTask.assignee_id == ctx.user_id)
    else:
        condition = scope_condition(ctx, WorkflowTask)
        if condition is not None:
            stmt = stmt.where(condition)
    if status:
        stmt = stmt.where(WorkflowTask.status == status)
    if biz_type:
        stmt = stmt.where(WorkflowInstance.biz_type == biz_type)
    if keyword:
        stmt = stmt.where(WorkflowInstance.title.like(f"%{keyword}%"))
    stmt = stmt.order_by(WorkflowTask.id.desc())
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())
    rows = db.execute(stmt.limit(params.page_size).offset(params.offset)).all()
    return {
        "items": [{"task": task, "instance": instance} for task, instance in rows],
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
    }


def get_instance(db: Session, ctx: ScopeContext, instance_id: int) -> WorkflowInstance:
    stmt = select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
    condition = scope_condition(ctx, WorkflowInstance)
    if condition is not None:
        stmt = stmt.where(condition)
    instance = db.execute(stmt).scalar_one_or_none()
    if instance is None:
        raise NotFoundError("流程实例不存在或无权访问")
    cc = db.execute(
        select(WorkflowCc.id).where(
            WorkflowCc.instance_id == instance.id, WorkflowCc.user_id == ctx.user_id
        ).limit(1)
    ).first()
    if (
        instance.initiator_id != ctx.user_id
        and not ctx.has_all
        and cc is None
        and not db.execute(
            select(WorkflowTask.id).where(
                WorkflowTask.instance_id == instance.id, WorkflowTask.assignee_id == ctx.user_id
            ).limit(1)
        ).first()
    ):
        raise ForbiddenError("无权查看该流程")
    return instance


def instance_detail(db: Session, ctx: ScopeContext, instance_id: int) -> dict:
    instance = get_instance(db, ctx, instance_id)
    tasks = list(
        db.execute(select(WorkflowTask).where(WorkflowTask.instance_id == instance.id).order_by(WorkflowTask.id))
        .scalars()
        .all()
    )
    records = list(
        db.execute(select(WorkflowRecord).where(WorkflowRecord.instance_id == instance.id).order_by(WorkflowRecord.id))
        .scalars()
        .all()
    )
    ccs = list(db.execute(select(WorkflowCc).where(WorkflowCc.instance_id == instance.id)).scalars().all())
    return {"instance": instance, "tasks": tasks, "records": records, "ccs": ccs}


def act(
    db: Session,
    user: User,
    instance_id: int,
    *,
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
    return engine.act(
        db,
        user=user,
        instance_id=instance_id,
        action=action,
        task_id=task_id,
        comment=comment,
        target_user_id=target_user_id,
        target_user_ids=target_user_ids,
        back_to=back_to,
        mode=mode,
        cc_user_ids=cc_user_ids,
        attachments=attachments,
    )


def list_definitions(db: Session, ctx: ScopeContext) -> list[WorkflowDefinition]:
    return list(
        db.execute(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.company_id == ctx.company_id)
            .order_by(WorkflowDefinition.code, WorkflowDefinition.version.desc())
        )
        .scalars()
        .all()
    )


def save_definition(db: Session, user: User, payload: dict[str, Any]) -> WorkflowDefinition:
    return engine.save_definition(
        db,
        user=user,
        code=str(payload.get("code") or "").upper(),
        name=str(payload.get("name") or "").strip(),
        nodes_json=payload.get("nodes_json") or {},
        enabled=bool(payload.get("enabled", True)),
        remark=payload.get("remark"),
    )
