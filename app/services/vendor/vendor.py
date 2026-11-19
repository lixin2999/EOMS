from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.core.security import encrypt_text
from app.models.enums import VendorLevel, VendorStatus, VendorType
from app.models.iam import User
from app.models.vendor import (
    Contract,
    Vendor,
    VendorBank,
    VendorContact,
    VendorLicense,
)
from app.models.workflow import WorkflowInstance
from app.services.common import company_code, ensure_files
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import to_date, today
from app.utils.numbering import next_no
from app.workflow import engine

VENDOR_TYPES = {item.value for item in VendorType}
VENDOR_STATUSES = {item.value for item in VendorStatus}
SENSITIVE_PERMISSION = "vendor:sensitive"


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Vendor)
    condition = scope_condition(ctx, Vendor, project_attr=None)
    return stmt.where(condition) if condition is not None else stmt


def list_vendors(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str | None = None,
    vendor_type: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if status:
        stmt = stmt.where(Vendor.status == status)
    if vendor_type:
        stmt = stmt.where(Vendor.type == vendor_type)
    if level:
        stmt = stmt.where(Vendor.level == level)
    if keyword:
        stmt = stmt.where(or_(Vendor.name.like(f"%{keyword}%"), Vendor.code.like(f"%{keyword}%")))
    stmt = stmt.order_by(Vendor.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_vendor(db: Session, ctx: ScopeContext, vendor_id: int) -> Vendor:
    vendor = db.execute(_base_query(ctx).where(Vendor.id == vendor_id)).scalar_one_or_none()
    if vendor is None:
        raise NotFoundError("供应商不存在或无权访问")
    return vendor


def create_vendor(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Vendor:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("供应商名称不能为空")
    vendor_type = str(payload.get("type") or "SERVICE")
    if vendor_type not in VENDOR_TYPES:
        raise BusinessRuleError("供应商分类非法")
    vendor = Vendor(
        company_id=user.company_id,
        dept_id=user.dept_id,
        creator_id=user.id,
        code=next_no(db, "VD", company_code=company_code(db, user.company_id), period=str(today().year)),
        name=name[:255],
        tax_no=(payload.get("tax_no") or "")[:64] or None,
        type=vendor_type,
        level="C",
        status=VendorStatus.PENDING.value,
        owner_user_id=payload.get("owner_user_id") or user.id,
        intro=(payload.get("intro") or "")[:2000],
    )
    db.add(vendor)
    db.flush()
    for contact in payload.get("contacts") or []:
        add_contact(db, user, vendor, contact)
    for bank in payload.get("banks") or []:
        add_bank(db, user, vendor, bank)
    for license_row in payload.get("licenses") or []:
        add_license(db, user, vendor, license_row)
    write_audit(
        db, user=user, action="CREATE_VENDOR", target_type="VENDOR", target_id=vendor.id, after=snapshot(vendor)
    )
    if payload.get("submit", True):
        submit_vendor(db, user, ctx, vendor.id)
    return vendor


def update_vendor(db: Session, user: User, ctx: ScopeContext, vendor_id: int, payload: dict[str, Any]) -> Vendor:
    vendor = get_vendor(db, ctx, vendor_id)
    if vendor.status == "BLACKLIST":
        raise BusinessRuleError("黑名单供应商不能修改，请先解除黑名单")
    expected = payload.get("version")
    if expected is not None and int(expected) != vendor.version:
        raise ConflictError("供应商已被修改，请刷新后重试")
    before = snapshot(vendor)
    if payload.get("name") is not None and str(payload["name"]).strip():
        vendor.name = str(payload["name"]).strip()[:255]
    if payload.get("tax_no") is not None:
        vendor.tax_no = str(payload["tax_no"])[:64] or None
    if payload.get("type") is not None:
        if payload["type"] not in VENDOR_TYPES:
            raise BusinessRuleError("供应商分类非法")
        vendor.type = payload["type"]
    if payload.get("owner_user_id") is not None:
        owner = db.get(User, int(payload["owner_user_id"]))
        if owner is None or owner.company_id != vendor.company_id:
            raise BusinessRuleError("负责人不存在")
        vendor.owner_user_id = owner.id
    if payload.get("intro") is not None:
        vendor.intro = str(payload["intro"])[:2000]
    if payload.get("level") is not None:
        if payload["level"] not in {item.value for item in VendorLevel}:
            raise BusinessRuleError("供应商等级非法")
        vendor.level = payload["level"]
    vendor.version = int(vendor.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_VENDOR",
        target_type="VENDOR",
        target_id=vendor.id,
        before=before,
        after=snapshot(vendor),
    )
    return vendor


def submit_vendor(db: Session, user: User, ctx: ScopeContext, vendor_id: int) -> Vendor:
    vendor = get_vendor(db, ctx, vendor_id)
    if vendor.status != VendorStatus.PENDING.value:
        raise BusinessRuleError("仅待审核供应商可提交准入")
    if not db.execute(select(VendorLicense.id).where(VendorLicense.vendor_id == vendor.id).limit(1)).first():
        raise BusinessRuleError("请先录入营业执照等资质信息")
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=vendor.dept_id,
        project_id=None,
        initiator=user,
        def_code="VENDOR_ONBOARD",
        biz_type="VENDOR_ONBOARD",
        biz_id=vendor.id,
        title=f"供应商准入：{vendor.code} {vendor.name}",
        context={"type": vendor.type, "vendor_id": vendor.id, "vendor_name": vendor.name, "amount": "0"},
    )
    vendor.instance_id = instance.id
    db.flush()
    write_audit(db, user=user, action="SUBMIT_VENDOR", target_type="VENDOR", target_id=vendor.id)
    return vendor


def blacklist_vendor(db: Session, user: User, ctx: ScopeContext, vendor_id: int, reason: str) -> Vendor:
    if not reason or len(reason.strip()) < 3:
        raise BusinessRuleError("请填写加入黑名单的原因")
    vendor = get_vendor(db, ctx, vendor_id)
    vendor.status = VendorStatus.BLACKLIST.value
    vendor.blacklist_reason = reason.strip()[:500]
    db.flush()
    write_audit(
        db,
        user=user,
        action="BLACKLIST_VENDOR",
        target_type="VENDOR",
        target_id=vendor.id,
        before={"status": "ACTIVE"},
        after={"reason": reason},
    )
    return vendor


def restore_vendor(db: Session, user: User, ctx: ScopeContext, vendor_id: int) -> Vendor:
    vendor = get_vendor(db, ctx, vendor_id)
    if vendor.status != "BLACKLIST":
        raise BusinessRuleError("供应商不在黑名单中")
    vendor.status = VendorStatus.ACTIVE.value
    vendor.blacklist_reason = None
    db.flush()
    write_audit(db, user=user, action="RESTORE_VENDOR", target_type="VENDOR", target_id=vendor.id)
    return vendor


def on_vendor_approved(db: Session, instance: WorkflowInstance) -> None:
    vendor = db.get(Vendor, instance.biz_id)
    if vendor is None:
        raise BusinessRuleError("供应商不存在")
    vendor.status = VendorStatus.ACTIVE.value
    db.flush()
    write_audit(
        db,
        user=None,
        action="VENDOR_APPROVED",
        target_type="VENDOR",
        target_id=vendor.id,
        company_id=vendor.company_id,
    )
    notify_with_email(
        db,
        company_id=vendor.company_id,
        user_ids=[vendor.owner_user_id] if vendor.owner_user_id else [],
        title=f"供应商准入通过：{vendor.name}",
        content=f"供应商 {vendor.code} 已通过准入审核。",
        type="APPROVAL",
        biz_type="VENDOR_ONBOARD",
        biz_id=vendor.id,
        link=f"/vendors/{vendor.id}",
        email=True,
    )


def on_vendor_rejected(db: Session, instance: WorkflowInstance) -> None:
    vendor = db.get(Vendor, instance.biz_id)
    if vendor:
        vendor.status = VendorStatus.PENDING.value
        db.flush()


# ---------------------------------------------------------------- 联系人 / 银行 / 资质
def list_contacts(db: Session, ctx: ScopeContext, vendor_id: int) -> list[VendorContact]:
    get_vendor(db, ctx, vendor_id)
    return list(
        db.execute(select(VendorContact).where(VendorContact.vendor_id == vendor_id).order_by(VendorContact.id))
        .scalars()
        .all()
    )


def add_contact(db: Session, user: User, vendor: Vendor, payload: dict[str, Any]) -> VendorContact:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("联系人姓名不能为空")
    item = VendorContact(
        company_id=vendor.company_id,
        vendor_id=vendor.id,
        name=name[:64],
        title=(payload.get("title") or "")[:64] or None,
        phone_enc=encrypt_text(str(payload.get("phone") or "")) or None,
        email=(payload.get("email") or "")[:128] or None,
        is_default=bool(payload.get("is_default")),
    )
    if item.is_default:
        _clear_default(db, VendorContact, vendor.id)
    db.add(item)
    db.flush()
    write_audit(
        db, user=user, action="ADD_VENDOR_CONTACT", target_type="VENDOR", target_id=vendor.id, after={"name": name}
    )
    return item


def list_banks(db: Session, ctx: ScopeContext, vendor_id: int) -> list[VendorBank]:
    get_vendor(db, ctx, vendor_id)
    return list(
        db.execute(select(VendorBank).where(VendorBank.vendor_id == vendor_id).order_by(VendorBank.id))
        .scalars()
        .all()
    )


def add_bank(db: Session, user: User, vendor: Vendor, payload: dict[str, Any]) -> VendorBank:
    account_no = str(payload.get("account_no") or "").strip()
    bank_name = str(payload.get("bank_name") or "").strip()
    account_name = str(payload.get("account_name") or "").strip()
    if not account_no or not bank_name or not account_name:
        raise BusinessRuleError("请完整填写开户行、账号与户名")
    if not account_no.isdigit() or not (8 <= len(account_no) <= 32):
        raise BusinessRuleError("银行账号格式不正确")
    item = VendorBank(
        company_id=vendor.company_id,
        vendor_id=vendor.id,
        bank_name=bank_name[:128],
        account_no_enc=encrypt_text(account_no),
        account_name=account_name[:128],
        is_default=bool(payload.get("is_default")),
    )
    if item.is_default:
        _clear_default(db, VendorBank, vendor.id)
    db.add(item)
    db.flush()
    write_audit(
        db,
        user=user,
        action="ADD_VENDOR_BANK",
        target_type="VENDOR",
        target_id=vendor.id,
        after={"bank_name": bank_name},
    )
    return item


def list_licenses(db: Session, ctx: ScopeContext, vendor_id: int) -> list[VendorLicense]:
    get_vendor(db, ctx, vendor_id)
    return list(
        db.execute(select(VendorLicense).where(VendorLicense.vendor_id == vendor_id).order_by(VendorLicense.valid_to))
        .scalars()
        .all()
    )


def add_license(db: Session, user: User, vendor: Vendor, payload: dict[str, Any]) -> VendorLicense:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("资质名称不能为空")
    valid_from = to_date(payload.get("valid_from"))
    valid_to = to_date(payload.get("valid_to"))
    if valid_from and valid_to and valid_to < valid_from:
        raise BusinessRuleError("资质有效期结束日期不能早于开始日期")
    file_id = payload.get("file_id")
    if file_id:
        ensure_files(db, [int(file_id)], vendor.company_id)
    item = VendorLicense(
        company_id=vendor.company_id,
        vendor_id=vendor.id,
        name=name[:128],
        no=(payload.get("no") or "")[:128] or None,
        file_id=int(file_id) if file_id else None,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(item)
    db.flush()
    write_audit(
        db, user=user, action="ADD_VENDOR_LICENSE", target_type="VENDOR", target_id=vendor.id, after={"name": name}
    )
    return item


def _clear_default(db: Session, model, vendor_id: int) -> None:
    rows = db.execute(select(model).where(model.vendor_id == vendor_id, model.is_default.is_(True))).scalars()
    for row in rows:
        row.is_default = False
    db.flush()


# ---------------------------------------------------------------- 供应商风险
def vendor_risks(db: Session, ctx: ScopeContext) -> list[dict]:
    today_value = today()
    result: list[dict] = []
    vendors = list(db.execute(_base_query(ctx)).scalars().all())
    vendor_ids = [vendor.id for vendor in vendors]
    if not vendor_ids:
        return result
    licenses = db.execute(
        select(VendorLicense).where(
            VendorLicense.vendor_id.in_(vendor_ids),
            VendorLicense.valid_to.is_not(None),
            VendorLicense.valid_to <= today_value.replace(year=today_value.year + 1),
        )
    ).scalars()
    for license_row in licenses:
        valid_to = license_row.valid_to
        if valid_to is None:
            continue
        days = (valid_to - today_value).days
        if days <= 30:
            result.append(
                {
                    "type": "LICENSE_EXPIRING",
                    "level": "HIGH" if days <= 7 else "MEDIUM",
                    "vendor_id": license_row.vendor_id,
                    "title": f"资质「{license_row.name}」将在 {days} 天后到期",
                    "date": valid_to.isoformat(),
                }
            )
    contracts = db.execute(
        select(Contract).where(
            Contract.company_id == ctx.company_id,
            Contract.status == "ACTIVE",
            Contract.end_date.is_not(None),
            Contract.end_date <= today_value.replace(year=today_value.year + 1),
        )
    ).scalars()
    for contract in contracts:
        days = (contract.end_date - today_value).days if contract.end_date else 0
        if days <= 30:
            result.append(
                {
                    "type": "CONTRACT_EXPIRING",
                    "level": "HIGH" if days <= 7 else "MEDIUM",
                    "vendor_id": contract.vendor_id,
                    "title": f"合同「{contract.no}」将在 {days} 天后到期",
                    "date": contract.end_date.isoformat() if contract.end_date else None,
                }
            )
    return result
