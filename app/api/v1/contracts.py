"""合同管理：主档、付款条款、状态流转、到期与超付风险。"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.response import ok
from app.api.serializers import file_brief, to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.finance import Payment
from app.models.iam import SysFile, User
from app.models.project import Project
from app.models.vendor import Vendor
from app.schemas.common import ContractIn, ContractStatusIn
from app.services.vendor import contract as contract_service

router = APIRouter(prefix="/contracts", tags=["合同管理"])

VIEW = Depends(require_permission("contract:view"))
MANAGE = Depends(require_permission("contract:manage"))


def _vendor_names(db, vendor_ids: Iterable[int]) -> dict[int, str]:
    ids = {int(item) for item in vendor_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Vendor.id, Vendor.name).where(Vendor.id.in_(ids))).all()
    return {int(vid): name for vid, name in rows}


def _project_names(db, project_ids: Iterable[int]) -> dict[int, str]:
    ids = {int(item) for item in project_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(Project.id, Project.name).where(Project.id.in_(ids))).all()
    return {int(pid): name for pid, name in rows}


def _files(db, file_ids: Iterable[int]) -> dict[int, dict]:
    ids = {int(item) for item in file_ids if item}
    if not ids:
        return {}
    rows = db.execute(select(SysFile).where(SysFile.id.in_(ids))).scalars().all()
    return {item.id: file_brief(item) for item in rows}


def _contract_row(db, item) -> dict:
    data = to_dict(item)
    data["vendor_name"] = _vendor_names(db, [item.vendor_id]).get(item.vendor_id, "")
    if item.project_id:
        data["project_name"] = _project_names(db, [item.project_id]).get(item.project_id, "")
    else:
        data["project_name"] = ""
    return data


@router.get("", summary="合同列表", dependencies=[VIEW])
def list_contracts(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    vendor_id: int | None = None,
    project_id: int | None = None,
    status: str | None = None,
    keyword: str | None = None,
    expiring_days: int | None = None,
) -> dict:
    result = contract_service.list_contracts(
        db,
        ctx,
        params,
        vendor_id=vendor_id,
        project_id=project_id,
        status=status,
        keyword=keyword,
        expiring_days=expiring_days,
    )
    return ok(
        {
            "items": [_contract_row(db, item) for item in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("", summary="新建合同", dependencies=[MANAGE])
def create_contract(payload: ContractIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = contract_service.create_contract(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(_contract_row(db, item), "合同已创建")


@router.get("/risks", summary="合同到期/超付风险", dependencies=[VIEW])
def contract_risks(db: DbSession, ctx: Scope, warning_days: int = 45) -> dict:
    return ok(contract_service.contract_risks(db, ctx, warning_days=warning_days))


@router.get("/{contract_id}", summary="合同详情", dependencies=[VIEW])
def get_contract(contract_id: int, db: DbSession, ctx: Scope) -> dict:
    item = contract_service.get_contract(db, ctx, contract_id)
    data = _contract_row(db, item)
    data["file"] = _files(db, [item.file_id] if item.file_id else []).get(item.file_id or 0, {})
    payments = list(
        db.execute(
            select(Payment).where(Payment.contract_id == item.id).order_by(Payment.id.desc()).limit(50)
        )
        .scalars()
        .all()
    )
    data["payments"] = [to_dict(row) for row in payments]
    paid = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.contract_id == item.id, Payment.status == "PAID"
        )
    ).scalar_one()
    data["paid_amount"] = float(paid or 0)
    data["unpaid_amount"] = float(Decimal(str(item.amount or 0)) - Decimal(str(paid or 0)))
    data["payment_ratio"] = (
        round(float(Decimal(str(paid or 0)) / Decimal(str(item.amount)) * 100), 2)
        if Decimal(str(item.amount or 0))
        else 0.0
    )
    return ok(data)


@router.put("/{contract_id}", summary="更新合同", dependencies=[MANAGE])
def update_contract(
    contract_id: int, payload: ContractIn, db: DbSession, user: CurrentUser, ctx: Scope
) -> dict:
    item = contract_service.update_contract(
        db, user, ctx, contract_id, payload.model_dump(exclude_unset=True)
    )
    return ok(_contract_row(db, item), "合同已更新")


@router.post("/{contract_id}/status", summary="变更合同状态", dependencies=[MANAGE])
def change_status(
    contract_id: int, payload: ContractStatusIn, db: DbSession, user: CurrentUser, ctx: Scope
) -> dict:
    item = contract_service.change_status(db, user, ctx, contract_id, payload.status, payload.reason)
    return ok(_contract_row(db, item), "合同状态已更新")


@router.get("/{contract_id}/payments", summary="合同付款记录", dependencies=[VIEW])
def contract_payments(contract_id: int, db: DbSession, ctx: Scope) -> dict:
    item = contract_service.get_contract(db, ctx, contract_id)
    rows = list(
        db.execute(select(Payment).where(Payment.contract_id == item.id).order_by(Payment.id.desc()))
        .scalars()
        .all()
    )
    names = {}
    applicant_ids = {row.applicant_id for row in rows if row.applicant_id}
    if applicant_ids:
        names = {
            int(uid): name
            for uid, name in db.execute(
                select(User.id, User.real_name).where(User.id.in_(applicant_ids))
            ).all()
        }
    return ok(
        [
            {**to_dict(row), "applicant_name": names.get(row.applicant_id, "")}
            for row in rows
        ]
    )
