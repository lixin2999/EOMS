"""元数据与下拉选项：前端表单/筛选统一数据源。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.response import ok
from app.core.deps import CurrentUser, DbSession, Scope
from app.core.scope import scope_condition
from app.models.enums import (
    AcceptanceResult,
    AccountType,
    BizType,
    ChangeType,
    ContractStatus,
    DocumentCategory,
    ExpenseType,
    IssueStatus,
    LeaveType,
    PaymentStatus,
    PermissionType,
    ProjectStage,
    ProjectStatus,
    ProjectType,
    ReceiptStatus,
    ReportCode,
    RevenueStatus,
    SecretLevel,
    VendorLevel,
    VendorStatus,
    VendorType,
)
from app.models.finance import Account
from app.models.iam import Dept, Role, SysDict, User
from app.models.project import Project
from app.models.vendor import Contract, Vendor
from app.services.iam import admin

router = APIRouter(prefix="/meta", tags=["元数据"])


def _enum_options(enum_cls) -> list[dict[str, str]]:
    return [{"value": item.value, "label": item.value} for item in enum_cls]


ENUMS: dict[str, list[dict[str, str]]] = {
    "expense_type": _enum_options(ExpenseType),
    "leave_type": _enum_options(LeaveType),
    "document_category": _enum_options(DocumentCategory),
    "secret_level": _enum_options(SecretLevel),
    "project_type": _enum_options(ProjectType),
    "project_stage": _enum_options(ProjectStage),
    "project_status": _enum_options(ProjectStatus),
    "change_type": _enum_options(ChangeType),
    "issue_status": _enum_options(IssueStatus),
    "acceptance_result": _enum_options(AcceptanceResult),
    "vendor_type": _enum_options(VendorType),
    "vendor_status": _enum_options(VendorStatus),
    "vendor_level": _enum_options(VendorLevel),
    "contract_status": _enum_options(ContractStatus),
    "payment_status": _enum_options(PaymentStatus),
    "receipt_status": _enum_options(ReceiptStatus),
    "revenue_status": _enum_options(RevenueStatus),
    "account_type": _enum_options(AccountType),
    "biz_type": _enum_options(BizType),
    "report_code": _enum_options(ReportCode),
    "permission_type": _enum_options(PermissionType),
    "task_status": [
        {"value": "TODO", "label": "待开始"},
        {"value": "DOING", "label": "进行中"},
        {"value": "DONE", "label": "已完成"},
        {"value": "BLOCKED", "label": "受阻"},
    ],
    "priority": [
        {"value": "LOW", "label": "低"},
        {"value": "MEDIUM", "label": "中"},
        {"value": "HIGH", "label": "高"},
        {"value": "URGENT", "label": "紧急"},
    ],
}

LABELS: dict[str, str] = {
    "TRAVEL": "差旅费",
    "ENTERTAIN": "业务招待费",
    "OFFICE": "办公费",
    "SUBCONTRACT": "分包费",
    "MATERIAL": "材料费",
    "OTHER": "其他",
    "ANNUAL": "年假",
    "PERSONAL": "事假",
    "SICK": "病假",
    "COMP": "调休",
    "PASS": "通过",
    "CONDITIONAL": "有条件通过",
    "FAIL": "未通过",
    "TODO": "待开始",
    "DOING": "进行中",
    "DONE": "已完成",
    "BLOCKED": "受阻",
    "OPEN": "待处理",
    "PROCESSING": "处理中",
    "CLOSED": "已关闭",
    "DRAFT": "草稿",
    "RUNNING": "审批中",
    "REJECTED": "已驳回",
    "APPROVED": "已通过",
    "VERIFIED": "已复核",
    "PAID": "已付款",
    "ARCHIVED": "已归档",
    "CANCELED": "已取消",
    "PENDING": "待处理",
    "REGISTERED": "已登记",
    "CONFIRMED": "已确认",
    "ACTIVE": "生效",
    "EXPIRED": "已到期",
    "TERMINATED": "已终止",
    "BLACKLIST": "黑名单",
    "SUSPENDED": "已暂停",
    "LAUNCH": "立项",
    "PLAN": "计划",
    "PLAN_CONFIRMED": "计划已确认",
    "EXECUTE": "执行",
    "CLOSE": "收尾",
}

ROLE_LABELS = {
    "SUPER_ADMIN": "系统管理员",
    "DIRECTOR": "董事",
    "MANAGER": "部门经理",
    "FINANCE": "财务",
    "PM": "项目经理",
    "MEMBER": "员工",
    "PROCUREMENT": "采购",
    "AUDITOR": "审计",
    "ADMIN": "行政",
}


def _labels(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in pairs]


@router.get("/enums", summary="枚举字典")
def enums() -> dict:
    return ok(
        {
            "enums": ENUMS,
            "labels": LABELS,
            "roles": ROLE_LABELS,
            "dicts": {},
        }
    )


@router.get("/options", summary="通用下拉选项")
def options(
    db: DbSession,
    ctx: Scope,
    keyword: str | None = Query(default=None, max_length=64),
) -> dict:
    """返回用户、部门、项目、客户、供应商、合同、科目、角色等选项。

    选项接口只返回当前用户可见范围内、状态有效的数据，避免前端越权探测。
    """
    user_stmt = select(User).where(User.company_id == ctx.company_id, User.status == "ACTIVE")
    if keyword:
        user_stmt = user_stmt.where(or_(User.real_name.like(f"%{keyword}%"), User.username.like(f"%{keyword}%")))
    users = list(db.execute(user_stmt.order_by(User.id).limit(1000)).scalars().all())

    depts = list(
        db.execute(select(Dept).where(Dept.company_id == ctx.company_id).order_by(Dept.sort, Dept.id)).scalars().all()
    )
    dept_nodes: dict[int, dict[str, Any]] = {
        item.id: {"id": item.id, "name": item.name, "parent_id": item.parent_id, "path": item.path, "children": []}
        for item in depts
    }
    dept_roots: list[dict] = []
    for item in depts:
        node = dept_nodes[item.id]
        parent = dept_nodes.get(item.parent_id or -1)
        if parent:
            parent["children"].append(node)
        else:
            dept_roots.append(node)

    project_stmt = select(Project).where(
        Project.company_id == ctx.company_id, Project.status.notin_(["CLOSED", "ARCHIVED", "CANCELED"])
    )
    condition = scope_condition(ctx, Project, project_attr="id")
    if condition is not None:
        project_stmt = project_stmt.where(condition)
    projects = list(db.execute(project_stmt.order_by(Project.id.desc()).limit(1000)).scalars().all())

    vendors = list(
        db.execute(
            select(Vendor)
            .where(Vendor.company_id == ctx.company_id, Vendor.status.in_(["ACTIVE", "SUSPENDED"]))
            .order_by(Vendor.id.desc())
            .limit(1000)
        )
        .scalars()
        .all()
    )
    contracts = list(
        db.execute(
            select(Contract)
            .where(Contract.company_id == ctx.company_id, Contract.status.in_(["DRAFT", "ACTIVE"]))
            .order_by(Contract.id.desc())
            .limit(1000)
        )
        .scalars()
        .all()
    )
    accounts = list(
        db.execute(
            select(Account)
            .where(Account.company_id == ctx.company_id, Account.status == "ACTIVE")
            .order_by(Account.code)
        )
        .scalars()
        .all()
    )
    roles = list(
        db.execute(
            select(Role)
            .where(or_(Role.company_id.is_(None), Role.company_id == ctx.company_id), Role.status == "ACTIVE")
            .order_by(Role.id)
        )
        .scalars()
        .all()
    )
    customers = admin.list_customers(db, ctx, keyword)

    return ok(
        {
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "real_name": user.real_name,
                    "dept_id": user.dept_id,
                    "position": user.position,
                }
                for user in users
            ],
            "depts": dept_roots,
            "projects": [
                {
                    "id": project.id,
                    "no": project.no,
                    "name": project.name,
                    "status": project.status,
                    "stage": project.stage,
                    "manager_id": project.manager_id,
                    "dept_id": project.dept_id,
                }
                for project in projects
            ],
            "vendors": [
                {
                    "id": vendor.id,
                    "code": vendor.code,
                    "name": vendor.name,
                    "type": vendor.type,
                    "status": vendor.status,
                }
                for vendor in vendors
            ],
            "contracts": [
                {
                    "id": contract.id,
                    "no": contract.no,
                    "name": contract.name,
                    "vendor_id": contract.vendor_id,
                    "project_id": contract.project_id,
                    "amount": float(contract.amount or 0),
                    "status": contract.status,
                }
                for contract in contracts
            ],
            "accounts": [
                {"code": account.code, "name": account.name, "type": account.type} for account in accounts
            ],
            "roles": [
                {"id": role.id, "code": role.code, "name": role.name, "data_scope": role.data_scope} for role in roles
            ],
            "customers": [admin.serialize_customer(item) for item in customers],
            "labels": LABELS,
        }
    )


@router.get("/dicts", summary="业务字典（所有登录用户可见）")
def dicts(db: DbSession, ctx: Scope, dict_type: str | None = None) -> dict:
    stmt = select(SysDict).where(
        or_(SysDict.company_id.is_(None), SysDict.company_id == ctx.company_id), SysDict.status == "ACTIVE"
    )
    if dict_type:
        stmt = stmt.where(SysDict.dict_type == dict_type)
    rows = list(db.execute(stmt.order_by(SysDict.dict_type, SysDict.sort, SysDict.id)).scalars().all())
    grouped: dict[str, list[dict]] = {}
    for item in rows:
        grouped.setdefault(item.dict_type, []).append({"value": item.value, "label": item.label})
    return ok(grouped)


@router.get("/me", summary="当前用户可用的元数据")
def me(db: DbSession, user: CurrentUser) -> dict:
    dept = db.get(Dept, user.dept_id) if user.dept_id else None
    return ok(
        {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "dept_id": user.dept_id,
            "dept_name": dept.name if dept else "",
            "position": user.position,
            "labels": LABELS,
        }
    )
