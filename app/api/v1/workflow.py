"""工作流：待办、实例详情、审批动作、流程定义。"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import User
from app.models.workflow import WorkflowDefinition, WorkflowInstance
from app.schemas.common import WorkflowActionIn, WorkflowDefinitionIn
from app.services import workflow_service
from app.workflow.definitions import DEFAULT_DEFINITIONS

router = APIRouter(prefix="/workflow", tags=["审批流程"])


def _name_map(db, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(User.id, User.real_name).where(User.id.in_(user_ids))).all()
    return {int(user_id): name for user_id, name in rows}


def _serialize_instance(instance: WorkflowInstance, names: dict[int, str]) -> dict:
    data = to_dict(instance)
    data["initiator_name"] = names.get(instance.initiator_id, "")
    data["status_label"] = instance.status
    return data


@router.get(
    "/instances",
    summary="流程实例列表",
    dependencies=[Depends(require_permission("workflow:instance"))],
)
def list_instances(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str | None = None,
    biz_type: str | None = None,
    keyword: str | None = None,
    mine: bool = False,
) -> dict:
    result = workflow_service.list_instances(
        db, ctx, params, status=status, biz_type=biz_type, keyword=keyword, mine=mine
    )
    names = _name_map(db, {item.initiator_id for item in result["items"]})
    return ok(
        {
            "items": [_serialize_instance(item, names) for item in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.get(
    "/instances/{instance_id}",
    summary="流程实例详情（含任务、记录、抄送）",
    dependencies=[Depends(require_permission("workflow:instance"))],
)
def instance_detail(instance_id: int, db: DbSession, ctx: Scope) -> dict:
    data = workflow_service.instance_detail(db, ctx, instance_id)
    instance = data["instance"]
    user_ids = {instance.initiator_id}
    user_ids.update(task.assignee_id for task in data["tasks"])
    user_ids.update(record.operator_id for record in data["records"])
    user_ids.update(cc.user_id for cc in data["ccs"])
    names = _name_map(db, user_ids)

    tasks = []
    for task in data["tasks"]:
        row = to_dict(task)
        row["assignee_name"] = names.get(task.assignee_id, "")
        tasks.append(row)
    records = []
    for record in data["records"]:
        row = to_dict(record)
        row["operator_name"] = record.operator_name or names.get(record.operator_id, "")
        records.append(row)
    ccs = []
    for cc in data["ccs"]:
        row = to_dict(cc)
        row["user_name"] = names.get(cc.user_id, "")
        ccs.append(row)

    return ok(
        {
            "instance": _serialize_instance(instance, names),
            "tasks": tasks,
            "records": records,
            "ccs": ccs,
            "definition": to_dict(db.get(WorkflowDefinition, instance.def_id)),
        }
    )


@router.post(
    "/instances/{instance_id}/actions",
    summary="执行审批动作（同意/驳回/转办/加签/撤回/催办/抄送）",
    dependencies=[Depends(require_permission("workflow:task"))],
)
def act(instance_id: int, payload: WorkflowActionIn, db: DbSession, user: CurrentUser) -> dict:
    instance = workflow_service.act(
        db,
        user,
        instance_id,
        action=payload.action,
        task_id=payload.task_id,
        comment=payload.comment,
        target_user_id=payload.target_user_id,
        target_user_ids=payload.target_user_ids,
        back_to=payload.back_to,
        mode=payload.mode,
        cc_user_ids=payload.cc_user_ids,
        attachments=payload.attachments,
    )
    return ok(to_dict(instance), "操作成功")


@router.get(
    "/tasks",
    summary="我的待办 / 流程待办",
    dependencies=[Depends(require_permission("workflow:task"))],
)
def list_tasks(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str = Query(default="PENDING"),
    mine: bool = True,
    biz_type: str | None = None,
    keyword: str | None = None,
) -> dict:
    result = workflow_service.list_tasks(
        db, ctx, params, status=status, mine=mine, biz_type=biz_type, keyword=keyword
    )
    items = result["items"]
    user_ids = {row["task"].assignee_id for row in items}
    user_ids.update(row["instance"].initiator_id for row in items)
    names = _name_map(db, user_ids)
    payload = []
    for row in items:
        task = row["task"]
        instance = row["instance"]
        data = to_dict(task)
        data["assignee_name"] = names.get(task.assignee_id, "")
        data["instance"] = _serialize_instance(instance, names)
        payload.append(data)
    return ok(
        {
            "items": payload,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.get(
    "/definitions",
    summary="流程定义列表",
    dependencies=[Depends(require_permission("workflow:definition"))],
)
def list_definitions(db: DbSession, ctx: Scope) -> dict:
    items = workflow_service.list_definitions(db, ctx)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[item.code].append(to_dict(item))
    current = {}
    for code, rows in grouped.items():
        enabled = next((row for row in rows if row.get("enabled")), rows[0])
        current[code] = enabled
    return ok({"items": [to_dict(item) for item in items], "current": list(current.values())})


@router.get("/definitions/defaults", summary="系统内置流程模板")
def default_definitions() -> dict:
    return ok(
        [
            {"code": code, "name": value["name"], "nodes_json": value["nodes_json"]}
            for code, value in DEFAULT_DEFINITIONS.items()
        ]
    )


@router.post(
    "/definitions",
    summary="保存流程定义（自动递增版本）",
    dependencies=[Depends(require_permission("workflow:definition"))],
)
def save_definition(payload: WorkflowDefinitionIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    definition = workflow_service.save_definition(db, user, payload.model_dump(exclude_unset=True))
    return ok(to_dict(definition), f"流程定义已保存（版本 {definition.version}）")
