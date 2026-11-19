"""审批业务：费用报销、请假、文件（用印/发文/制度）。"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import expense as serialize_expense
from app.api.serializers import file_brief, to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import SysFile, User
from app.models.project import Project
from app.schemas.common import (
    DocumentIn,
    DocumentUpdateIn,
    ExpenseIn,
    ExpenseUpdateIn,
    LeaveIn,
    LeaveUpdateIn,
)
from app.services.approval import document as document_service
from app.services.approval import expense as expense_service
from app.services.approval import leave as leave_service
from app.utils.datetime import to_datetime

router = APIRouter(prefix="/approvals", tags=["审批业务"])


def _names(db, user_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in user_ids if item}
    if not ids:
        return {}
    return {int(uid): name for uid, name in db.execute(select(User.id, User.real_name).where(User.id.in_(ids))).all()}


def _projects(db, project_ids: Iterable[int | None]) -> dict[int, str]:
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


def _files_of(expense) -> list[int]:
    ids = list(expense.invoices_file_ids or [])
    for item in expense.items_json or []:
        if item.get("file_id"):
            ids.append(int(item["file_id"]))
    return ids


# ------------------------------------------------------------------ 报销
@router.get(
    "/expenses",
    summary="报销单列表",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def list_expenses(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str | None = None,
    project_id: int | None = None,
    applicant_id: int | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    result = expense_service.list_expenses(
        db,
        ctx,
        params,
        status=status,
        project_id=project_id,
        applicant_id=applicant_id,
        keyword=keyword,
        date_from=to_datetime(date_from),
        date_to=to_datetime(date_to),
    )
    names = _names(db, (item.applicant_id for item in result["items"]))
    projects = _projects(db, (item.project_id for item in result["items"]))
    items = []
    for row in result["items"]:
        data = serialize_expense(row)
        data["applicant_name"] = names.get(row.applicant_id, "")
        data["project_name"] = projects.get(row.project_id or 0, "")
        items.append(data)
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post(
    "/expenses",
    summary="新建报销单（草稿）",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def create_expense(payload: ExpenseIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = expense_service.create_expense(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(serialize_expense(item), "报销单已创建")


@router.get(
    "/expenses/{expense_id}",
    summary="报销单详情",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def get_expense(expense_id: int, db: DbSession, ctx: Scope) -> dict:
    row = expense_service.get_expense(db, ctx, expense_id)
    data = serialize_expense(row)
    names = _names(db, [row.applicant_id])
    projects = _projects(db, [row.project_id])
    file_map = _files(db, _files_of(row))
    data["applicant_name"] = names.get(row.applicant_id, "")
    data["project_name"] = projects.get(row.project_id or 0, "")
    data["invoices"] = [file_map[item] for item in row.invoices_file_ids or [] if item in file_map]
    for item_row in data.get("items") or []:
        if isinstance(item_row, dict) and item_row.get("file_id") in file_map:
            item_row["file"] = file_map[item_row["file_id"]]
    return ok(data)


@router.put(
    "/expenses/{expense_id}",
    summary="修改报销单（草稿/驳回）",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def update_expense(expense_id: int, payload: ExpenseUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.update_expense(db, user, ctx, expense_id, payload.model_dump(exclude_unset=True))
    return ok(serialize_expense(row), "报销单已更新")


@router.post(
    "/expenses/{expense_id}/submit",
    summary="提交报销审批",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def submit_expense(expense_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.submit_expense(db, user, ctx, expense_id)
    return ok(serialize_expense(row), "已提交审批")


@router.post(
    "/expenses/{expense_id}/cancel",
    summary="取消报销单",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def cancel_expense(expense_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.cancel_expense(db, user, ctx, expense_id)
    return ok(serialize_expense(row), "报销单已取消")


@router.post(
    "/expenses/{expense_id}/withdraw",
    summary="撤回报销审批",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def withdraw_expense(expense_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.withdraw_expense(db, user, ctx, expense_id)
    return ok(serialize_expense(row), "审批已撤回")


@router.post(
    "/expenses/{expense_id}/verify",
    summary="财务复核报销单",
    dependencies=[Depends(require_permission("finance:payment"))],
)
def verify_expense(expense_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.finance_verify(db, user, ctx, expense_id)
    return ok(serialize_expense(row), "财务复核完成")


@router.post(
    "/expenses/{expense_id}/archive",
    summary="归档已付款报销单",
    dependencies=[Depends(require_permission("approval:expense"))],
)
def archive_expense(expense_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = expense_service.archive_expense(db, user, ctx, expense_id)
    return ok(serialize_expense(row), "报销单已归档")


# ------------------------------------------------------------------ 请假
@router.get(
    "/leaves/balance",
    summary="我的假期余额",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def leave_balance(db: DbSession, user: CurrentUser, year: int | None = None) -> dict:
    rows = leave_service.leave_balance_list(db, user, year)
    return ok([to_dict(item) for item in rows])


@router.get(
    "/leaves",
    summary="请假单列表",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def list_leaves(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str | None = None,
    leave_type: str | None = Query(default=None, alias="type"),
    applicant_id: int | None = None,
) -> dict:
    result = leave_service.list_leaves(
        db, ctx, params, status=status, leave_type=leave_type, applicant_id=applicant_id
    )
    names = _names(db, (item.applicant_id for item in result["items"]))
    projects = _projects(db, (item.project_id for item in result["items"]))
    items = []
    for row in result["items"]:
        data = to_dict(row)
        data["applicant_name"] = names.get(row.applicant_id, "")
        data["project_name"] = projects.get(row.project_id or 0, "")
        items.append(data)
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post(
    "/leaves",
    summary="新建请假单",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def create_leave(payload: LeaveIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = leave_service.create_leave(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "请假单已创建")


@router.get(
    "/leaves/{leave_id}",
    summary="请假单详情",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def get_leave(leave_id: int, db: DbSession, ctx: Scope) -> dict:
    row = leave_service.get_leave(db, ctx, leave_id)
    data = to_dict(row)
    data["applicant_name"] = _names(db, [row.applicant_id]).get(row.applicant_id, "")
    data["handover_name"] = _names(db, [row.handover_user_id]).get(row.handover_user_id or 0, "")
    data["project_name"] = _projects(db, [row.project_id]).get(row.project_id or 0, "")
    return ok(data)


@router.put(
    "/leaves/{leave_id}",
    summary="修改请假单（草稿/驳回）",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def update_leave(leave_id: int, payload: LeaveUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = leave_service.update_leave(db, user, ctx, leave_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "请假单已更新")


@router.post(
    "/leaves/{leave_id}/submit",
    summary="提交请假审批",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def submit_leave(leave_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = leave_service.submit_leave(db, user, ctx, leave_id)
    return ok(to_dict(row), "已提交审批")


@router.post(
    "/leaves/{leave_id}/cancel",
    summary="取消请假单",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def cancel_leave(leave_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = leave_service.cancel_leave(db, user, ctx, leave_id)
    return ok(to_dict(row), "请假单已取消")


@router.post(
    "/leaves/{leave_id}/withdraw",
    summary="撤回请假审批",
    dependencies=[Depends(require_permission("approval:leave"))],
)
def withdraw_leave(leave_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = leave_service.withdraw_leave(db, user, ctx, leave_id)
    return ok(to_dict(row), "审批已撤回")


# ------------------------------------------------------------------ 文件
@router.get(
    "/documents",
    summary="文件列表",
    dependencies=[Depends(require_permission("approval:document"))],
)
def list_documents(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
) -> dict:
    result = document_service.list_documents(db, ctx, params, status=status, category=category, keyword=keyword)
    names = _names(db, (item.creator_id for item in result["items"]))
    items = []
    for row in result["items"]:
        data = to_dict(row, exclude={"content"})
        data["creator_name"] = names.get(row.creator_id or 0, "")
        items.append(data)
    return ok(
        {
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post(
    "/documents",
    summary="新建文件",
    dependencies=[Depends(require_permission("approval:document"))],
)
def create_document(payload: DocumentIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = document_service.create_document(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "文件已创建")


@router.get(
    "/documents/{doc_id}",
    summary="文件详情",
    dependencies=[Depends(require_permission("approval:document"))],
)
def get_document(doc_id: int, db: DbSession, ctx: Scope) -> dict:
    row = document_service.get_document(db, ctx, doc_id)
    data = to_dict(row)
    data["creator_name"] = _names(db, [row.creator_id]).get(row.creator_id or 0, "")
    file_map = _files(db, [row.file_id] if row.file_id else [])
    data["file"] = file_map.get(row.file_id or 0, {})
    return ok(data)


@router.put(
    "/documents/{doc_id}",
    summary="修改文件（草稿/驳回）",
    dependencies=[Depends(require_permission("approval:document"))],
)
def update_document(doc_id: int, payload: DocumentUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = document_service.update_document(db, user, ctx, doc_id, payload.model_dump(exclude_unset=True))
    return ok(to_dict(row), "文件已更新")


@router.post(
    "/documents/{doc_id}/submit",
    summary="提交文件审批",
    dependencies=[Depends(require_permission("approval:document"))],
)
def submit_document(doc_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = document_service.submit_document(db, user, ctx, doc_id)
    return ok(to_dict(row), "已提交审批")


@router.post(
    "/documents/{doc_id}/cancel",
    summary="取消文件",
    dependencies=[Depends(require_permission("approval:document"))],
)
def cancel_document(doc_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = document_service.cancel_document(db, user, ctx, doc_id)
    return ok(to_dict(row), "文件已取消")


@router.post(
    "/documents/{doc_id}/withdraw",
    summary="撤回文件审批",
    dependencies=[Depends(require_permission("approval:document"))],
)
def withdraw_document(doc_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    row = document_service.withdraw_document(db, user, ctx, doc_id)
    return ok(to_dict(row), "审批已撤回")
