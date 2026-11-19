"""供应商管理：主档、准入、联系人/银行/资质、项目关联、评价与风险。"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import bank as serialize_bank
from app.api.serializers import contact as serialize_contact
from app.api.serializers import file_brief, to_dict
from app.api.serializers import vendor as serialize_vendor
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import SysFile, User
from app.models.project import Project
from app.models.vendor import Contract, Vendor
from app.schemas.common import (
    BankIn,
    BindProjectIn,
    BlacklistIn,
    ContactIn,
    EvaluationIn,
    LicenseIn,
    VendorIn,
    VendorUpdateIn,
)
from app.services.vendor import contract as contract_service
from app.services.vendor import evaluation as evaluation_service
from app.services.vendor import vendor as vendor_service

router = APIRouter(prefix="/vendors", tags=["供应商管理"])

VIEW = Depends(require_permission("vendor:view"))
CREATE = Depends(require_permission("vendor:create"))
MANAGE = Depends(require_permission("vendor:manage"))
EVALUATE = Depends(require_permission("vendor:evaluate"))


def _names(db, user_ids: Iterable[int | None]) -> dict[int, str]:
    ids = {int(item) for item in user_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.real_name).where(User.id.in_(ids))).all()
    return {int(uid): name for uid, name in rows}


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


def _sensitive(ctx: Scope) -> bool:
    return ctx.is_super or ctx.has_perm("vendor:sensitive")


def _vendor_row(db, ctx: Scope, item: Vendor) -> dict:
    names = _names(db, [item.owner_user_id])
    data = serialize_vendor(item, sensitive=_sensitive(ctx))
    data["owner_name"] = names.get(item.owner_user_id or 0, "")
    return data


def _bank_row(item, sensitive: bool) -> dict:
    data = serialize_bank(item, sensitive=sensitive)
    data["display_account"] = data.get("account_no")
    return data


# ------------------------------------------------------------------ 主档
@router.get("", summary="供应商列表", dependencies=[VIEW])
def list_vendors(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    status: str | None = None,
    vendor_type: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
) -> dict:
    result = vendor_service.list_vendors(
        db, ctx, params, status=status, vendor_type=vendor_type, level=level, keyword=keyword
    )
    return ok(
        {
            "items": [_vendor_row(db, ctx, item) for item in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("", summary="新建供应商（可提交准入）", dependencies=[CREATE])
def create_vendor(payload: VendorIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = vendor_service.create_vendor(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(_vendor_row(db, ctx, item), "供应商已创建")


@router.get("/risks", summary="供应商资质/合同风险", dependencies=[VIEW])
def vendor_risks(db: DbSession, ctx: Scope) -> dict:
    return ok(vendor_service.vendor_risks(db, ctx))


@router.get("/{vendor_id}", summary="供应商详情", dependencies=[VIEW])
def get_vendor(vendor_id: int, db: DbSession, ctx: Scope) -> dict:
    item = vendor_service.get_vendor(db, ctx, vendor_id)
    data = _vendor_row(db, ctx, item)
    sensitive = _sensitive(ctx)
    data["contacts"] = [
        serialize_contact(row, sensitive=sensitive)
        for row in vendor_service.list_contacts(db, ctx, vendor_id)
    ]
    data["banks"] = [
        _bank_row(row, sensitive) for row in vendor_service.list_banks(db, ctx, vendor_id)
    ]
    licenses = vendor_service.list_licenses(db, ctx, vendor_id)
    file_map = _files(db, (row.file_id for row in licenses if row.file_id))
    data["licenses"] = [
        {**to_dict(row), "file": file_map.get(row.file_id or 0, {})} for row in licenses
    ]
    data["projects"] = [
        {**to_dict(row), "project_name": _projects(db, [row.project_id]).get(row.project_id, "")}
        for row in contract_service.list_vendor_projects(db, ctx, vendor_id)
    ]
    contracts = list(
        db.execute(
            select(Contract)
            .where(Contract.vendor_id == vendor_id)
            .order_by(Contract.id.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    data["contracts"] = [to_dict(row) for row in contracts]
    data["evaluations"] = [
        to_dict(row) for row in evaluation_service.list_evaluations(db, ctx, vendor_id)[:10]
    ]
    return ok(data)


@router.put("/{vendor_id}", summary="更新供应商", dependencies=[MANAGE])
def update_vendor(vendor_id: int, payload: VendorUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = vendor_service.update_vendor(
        db, user, ctx, vendor_id, payload.model_dump(exclude_unset=True)
    )
    return ok(_vendor_row(db, ctx, item), "供应商已更新")


@router.post("/{vendor_id}/submit", summary="提交供应商准入", dependencies=[MANAGE])
def submit_vendor(vendor_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = vendor_service.submit_vendor(db, user, ctx, vendor_id)
    return ok(_vendor_row(db, ctx, item), "供应商准入已提交")


@router.post("/{vendor_id}/blacklist", summary="加入黑名单", dependencies=[MANAGE])
def blacklist_vendor(vendor_id: int, payload: BlacklistIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = vendor_service.blacklist_vendor(db, user, ctx, vendor_id, payload.reason)
    return ok(_vendor_row(db, ctx, item), "供应商已加入黑名单")


@router.post("/{vendor_id}/restore", summary="解除黑名单", dependencies=[MANAGE])
def restore_vendor(vendor_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = vendor_service.restore_vendor(db, user, ctx, vendor_id)
    return ok(_vendor_row(db, ctx, item), "供应商已恢复")


# ------------------------------------------------------------------ 联系人 / 银行 / 资质
@router.get("/{vendor_id}/contacts", summary="供应商联系人", dependencies=[VIEW])
def list_contacts(
    vendor_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    sensitive = _sensitive(ctx)
    return ok(
        [
            serialize_contact(row, sensitive=sensitive)
            for row in vendor_service.list_contacts(db, ctx, vendor_id, limit=limit)
        ]
    )


@router.post("/{vendor_id}/contacts", summary="新增联系人", dependencies=[MANAGE])
def add_contact(vendor_id: int, payload: ContactIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    vendor = vendor_service.get_vendor(db, ctx, vendor_id)
    item = vendor_service.add_contact(db, user, vendor, payload.model_dump(exclude_unset=True))
    return ok(serialize_contact(item, sensitive=_sensitive(ctx)), "联系人已添加")


@router.get("/{vendor_id}/banks", summary="供应商银行账户", dependencies=[VIEW])
def list_banks(
    vendor_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    sensitive = _sensitive(ctx)
    return ok(
        [_bank_row(row, sensitive) for row in vendor_service.list_banks(db, ctx, vendor_id, limit=limit)]
    )


@router.post("/{vendor_id}/banks", summary="新增银行账户", dependencies=[MANAGE])
def add_bank(vendor_id: int, payload: BankIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    vendor = vendor_service.get_vendor(db, ctx, vendor_id)
    item = vendor_service.add_bank(db, user, vendor, payload.model_dump(exclude_unset=True))
    return ok(_bank_row(item, _sensitive(ctx)), "银行账户已添加")


@router.get("/{vendor_id}/licenses", summary="供应商资质", dependencies=[VIEW])
def list_licenses(
    vendor_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    rows = vendor_service.list_licenses(db, ctx, vendor_id, limit=limit)
    file_map = _files(db, (row.file_id for row in rows if row.file_id))
    return ok([{**to_dict(row), "file": file_map.get(row.file_id or 0, {})} for row in rows])


@router.post("/{vendor_id}/licenses", summary="新增资质", dependencies=[MANAGE])
def add_license(vendor_id: int, payload: LicenseIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    vendor = vendor_service.get_vendor(db, ctx, vendor_id)
    item = vendor_service.add_license(db, user, vendor, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "资质已添加")


# ------------------------------------------------------------------ 项目关联
@router.get("/{vendor_id}/projects", summary="供应商合作项目", dependencies=[VIEW])
def list_vendor_projects(
    vendor_id: int, db: DbSession, ctx: Scope, limit: int = Query(200, ge=1, le=500)
) -> dict:
    rows = contract_service.list_vendor_projects(db, ctx, vendor_id, limit=limit)
    projects = _projects(db, (row.project_id for row in rows))
    return ok([{**to_dict(row), "project_name": projects.get(row.project_id, "")} for row in rows])


@router.post("/{vendor_id}/projects", summary="关联合作项目", dependencies=[MANAGE])
def bind_project(vendor_id: int, payload: BindProjectIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = contract_service.bind_project(
        db, user, ctx, vendor_id, payload.model_dump(exclude_unset=True)
    )
    return ok(to_dict(item), "项目关联已建立")


# ------------------------------------------------------------------ 评价
@router.get("/{vendor_id}/evaluations", summary="供应商评价记录", dependencies=[VIEW])
def list_evaluations(
    vendor_id: int,
    db: DbSession,
    ctx: Scope,
    year: int | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    rows = evaluation_service.list_evaluations(db, ctx, vendor_id, year=year, limit=limit)
    names = _names(db, (row.evaluator_id for row in rows))
    projects = _projects(db, (row.project_id for row in rows if row.project_id))
    return ok(
        [
            {
                **to_dict(row),
                "evaluator_name": names.get(row.evaluator_id, ""),
                "project_name": projects.get(row.project_id or 0, ""),
            }
            for row in rows
        ]
    )


@router.post("/{vendor_id}/evaluations", summary="新增供应商评价", dependencies=[EVALUATE])
def create_evaluation(
    vendor_id: int, payload: EvaluationIn, db: DbSession, user: CurrentUser, ctx: Scope
) -> dict:
    item = evaluation_service.create_evaluation(
        db, user, ctx, vendor_id, payload.model_dump(exclude_unset=True)
    )
    return ok(to_dict(item), "评价已提交")


@router.get("/{vendor_id}/annual-report", summary="供应商年度评价报告", dependencies=[VIEW])
def annual_report(vendor_id: int, db: DbSession, ctx: Scope, year: int | None = None) -> dict:
    from app.utils.datetime import today

    return ok(evaluation_service.annual_report(db, ctx, vendor_id, year or today().year))
