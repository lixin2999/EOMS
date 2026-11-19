"""供应商合同：主档、付款条款、合同-项目关联、到期与超付风险。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, assert_project_access, scope_condition
from app.models.enums import ContractStatus
from app.models.iam import User
from app.models.project import Project
from app.models.vendor import Contract, Vendor, VendorProject
from app.services.common import company_code, ensure_files
from app.services.iam.audit import snapshot, write_audit
from app.utils.datetime import to_date, today
from app.utils.money import to_decimal
from app.utils.numbering import next_no

CONTRACT_STATUSES = {item.value for item in ContractStatus}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Contract)
    condition = scope_condition(ctx, Contract)
    return stmt.where(condition) if condition is not None else stmt


def list_contracts(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    vendor_id: int | None = None,
    project_id: int | None = None,
    status: str | None = None,
    keyword: str | None = None,
    expiring_days: int | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if vendor_id:
        stmt = stmt.where(Contract.vendor_id == vendor_id)
    if project_id:
        stmt = stmt.where(Contract.project_id == project_id)
    if status:
        stmt = stmt.where(Contract.status == status)
    if keyword:
        stmt = stmt.where(or_(Contract.name.like(f"%{keyword}%"), Contract.no.like(f"%{keyword}%")))
    if expiring_days is not None:
        deadline = today() + timedelta(days=max(expiring_days, 0))
        stmt = stmt.where(
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.end_date.is_not(None),
            Contract.end_date <= deadline,
        )
    stmt = stmt.order_by(Contract.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_contract(db: Session, ctx: ScopeContext, contract_id: int) -> Contract:
    contract = db.execute(_base_query(ctx).where(Contract.id == contract_id)).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("合同不存在或无权访问")
    return contract


def _validate_vendor(db: Session, ctx: ScopeContext, vendor_id: int) -> Vendor:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.company_id != ctx.company_id:
        raise BusinessRuleError("供应商不存在")
    if vendor.status == "BLACKLIST":
        raise BusinessRuleError("黑名单供应商不能签订合同")
    return vendor


def _validate_project(db: Session, ctx: ScopeContext, project_id: int | None) -> Project | None:
    if not project_id:
        return None
    project = db.get(Project, project_id)
    if project is None or project.company_id != ctx.company_id:
        raise BusinessRuleError("项目不存在")
    assert_project_access(db, ctx, project.id)
    if project.status in {"CLOSED", "ARCHIVED"}:
        raise BusinessRuleError("项目已关闭，不能新增合同")
    return project


def _normalize_terms(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise BusinessRuleError("付款条款必须是数组")
    if len(raw) > 20:
        raise BusinessRuleError("付款条款不得超过 20 条")
    result = []
    for row in raw:
        if not isinstance(row, dict):
            raise BusinessRuleError("付款条款格式不正确")
        amount = to_decimal(row.get("amount"), field_name="条款金额")
        if amount < 0:
            raise BusinessRuleError("付款条款金额不能为负数")
        result.append(
            {
                "name": str(row.get("name") or "付款节点")[:64],
                "ratio": float(row.get("ratio") or 0),
                "amount": str(amount),
                "due_date": str(to_date(row.get("due_date")) or ""),
                "remark": str(row.get("remark") or "")[:255],
            }
        )
    return result


def _upsert_vendor_project(db: Session, contract: Contract, vendor: Vendor) -> None:
    if not contract.project_id:
        return
    row = db.execute(
        select(VendorProject).where(
            VendorProject.vendor_id == vendor.id,
            VendorProject.project_id == contract.project_id,
            VendorProject.contract_id == contract.id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = VendorProject(
            company_id=vendor.company_id,
            vendor_id=vendor.id,
            project_id=contract.project_id,
            contract_id=contract.id,
            role="分包商",
            contract_amount=contract.amount,
            paid_amount=Decimal("0"),
            settled_amount=Decimal("0"),
            score=vendor.score,
        )
        db.add(row)
    else:
        row.contract_amount = contract.amount
    db.flush()


def create_contract(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Contract:
    vendor = _validate_vendor(db, ctx, int(payload.get("vendor_id") or 0))
    project = _validate_project(db, ctx, payload.get("project_id"))
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("合同名称不能为空")
    amount = to_decimal(payload.get("amount"), field_name="合同金额")
    if amount < 0:
        raise BusinessRuleError("合同金额不能为负数")
    sign_date = to_date(payload.get("sign_date"))
    start_date = to_date(payload.get("start_date"))
    end_date = to_date(payload.get("end_date"))
    if start_date and end_date and end_date < start_date:
        raise BusinessRuleError("合同结束日期不能早于开始日期")
    file_id = payload.get("file_id")
    file_ids = ensure_files(db, [file_id] if file_id else [], user.company_id)
    contract = Contract(
        company_id=user.company_id,
        dept_id=user.dept_id,
        project_id=project.id if project else None,
        creator_id=user.id,
        no=next_no(db, "HT", company_code=company_code(db, user.company_id), period=str(today().year)),
        vendor_id=vendor.id,
        name=name[:255],
        amount=amount,
        currency=str(payload.get("currency") or "CNY")[:8],
        sign_date=sign_date,
        start_date=start_date,
        end_date=end_date,
        pay_terms_json=_normalize_terms(payload.get("pay_terms") or payload.get("pay_terms_json")),
        file_id=file_ids[0] if file_ids else None,
        status=ContractStatus.ACTIVE.value if payload.get("activate") else ContractStatus.DRAFT.value,
        remark=(payload.get("remark") or "")[:1000],
    )
    if not contract.currency:
        raise BusinessRuleError("币种不能为空")
    db.add(contract)
    db.flush()
    _upsert_vendor_project(db, contract, vendor)
    write_audit(
        db, user=user, action="CREATE_CONTRACT", target_type="CONTRACT", target_id=contract.id, after=snapshot(contract)
    )
    return contract


def update_contract(
    db: Session, user: User, ctx: ScopeContext, contract_id: int, payload: dict[str, Any]
) -> Contract:
    contract = get_contract(db, ctx, contract_id)
    if contract.status == ContractStatus.TERMINATED.value:
        raise BusinessRuleError("已终止合同不能修改")
    expected = payload.get("version")
    if expected is not None and int(expected) != contract.version:
        raise ConflictError("合同已被修改，请刷新后重试")
    before = snapshot(contract)
    vendor = _validate_vendor(db, ctx, contract.vendor_id)
    if payload.get("name") is not None and str(payload["name"]).strip():
        contract.name = str(payload["name"]).strip()[:255]
    if payload.get("amount") is not None:
        amount = to_decimal(payload["amount"], field_name="合同金额")
        if amount < 0:
            raise BusinessRuleError("合同金额不能为负数")
        contract.amount = amount
    if payload.get("currency") is not None:
        contract.currency = str(payload["currency"])[:8] or "CNY"
    if payload.get("sign_date") is not None:
        contract.sign_date = to_date(payload["sign_date"])
    if payload.get("start_date") is not None:
        contract.start_date = to_date(payload["start_date"])
    if payload.get("end_date") is not None:
        contract.end_date = to_date(payload["end_date"])
    if contract.start_date and contract.end_date and contract.end_date < contract.start_date:
        raise BusinessRuleError("合同结束日期不能早于开始日期")
    if payload.get("project_id") is not None:
        project = _validate_project(db, ctx, payload["project_id"] or None)
        contract.project_id = project.id if project else None
    if payload.get("pay_terms") is not None or payload.get("pay_terms_json") is not None:
        contract.pay_terms_json = _normalize_terms(payload.get("pay_terms") or payload.get("pay_terms_json"))
    if payload.get("file_id") is not None:
        ids = ensure_files(db, [payload["file_id"]] if payload["file_id"] else [], user.company_id)
        contract.file_id = ids[0] if ids else None
    if payload.get("remark") is not None:
        contract.remark = str(payload["remark"])[:1000]
    if payload.get("status") is not None:
        status = str(payload["status"])
        if status not in CONTRACT_STATUSES:
            raise BusinessRuleError("合同状态非法")
        contract.status = status
    contract.version = int(contract.version or 1) + 1
    db.flush()
    _upsert_vendor_project(db, contract, vendor)
    write_audit(
        db,
        user=user,
        action="UPDATE_CONTRACT",
        target_type="CONTRACT",
        target_id=contract.id,
        before=before,
        after=snapshot(contract),
    )
    return contract


def change_status(
    db: Session, user: User, ctx: ScopeContext, contract_id: int, status: str, reason: str | None = None
) -> Contract:
    if status not in CONTRACT_STATUSES:
        raise BusinessRuleError("合同状态非法")
    contract = get_contract(db, ctx, contract_id)
    if contract.status == status:
        return contract
    if contract.status == ContractStatus.TERMINATED.value:
        raise BusinessRuleError("已终止合同不能变更状态")
    if status == ContractStatus.TERMINATED.value and not (reason and len(reason.strip()) >= 3):
        raise BusinessRuleError("终止合同必须填写原因")
    before = {"status": contract.status}
    contract.status = status
    contract.version = int(contract.version or 1) + 1
    if reason:
        contract.remark = (contract.remark or "")[:800] + f"｜{status}：{reason.strip()[:180]}"
    db.flush()
    write_audit(
        db,
        user=user,
        action=f"CONTRACT_{status}",
        target_type="CONTRACT",
        target_id=contract.id,
        before=before,
        after={"status": status, "reason": reason},
    )
    return contract


def list_vendor_projects(db: Session, ctx: ScopeContext, vendor_id: int, limit: int = 200) -> list[VendorProject]:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.company_id != ctx.company_id:
        raise NotFoundError("供应商不存在")
    return list(
        db.execute(
            select(VendorProject)
            .where(VendorProject.vendor_id == vendor_id)
            .order_by(VendorProject.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def bind_project(db: Session, user: User, ctx: ScopeContext, vendor_id: int, payload: dict[str, Any]) -> VendorProject:
    vendor = _validate_vendor(db, ctx, vendor_id)
    project = _validate_project(db, ctx, int(payload.get("project_id") or 0))
    if project is None:
        raise BusinessRuleError("请选择项目")
    contract_id = payload.get("contract_id")
    if contract_id:
        contract = get_contract(db, ctx, int(contract_id))
        if contract.vendor_id != vendor.id:
            raise BusinessRuleError("合同不属于该供应商")
    exists = db.execute(
        select(VendorProject).where(
            VendorProject.vendor_id == vendor.id,
            VendorProject.project_id == project.id,
            VendorProject.contract_id == (int(contract_id) if contract_id else None),
        )
    ).scalar_one_or_none()
    if exists:
        raise BusinessRuleError("该供应商已关联此项目/合同")
    row = VendorProject(
        company_id=vendor.company_id,
        vendor_id=vendor.id,
        project_id=project.id,
        contract_id=int(contract_id) if contract_id else None,
        role=str(payload.get("role") or "分包商")[:64],
        contract_amount=to_decimal(payload.get("contract_amount"), field_name="合同额"),
        paid_amount=Decimal("0"),
        settled_amount=Decimal("0"),
        score=vendor.score,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user=user,
        action="BIND_VENDOR_PROJECT",
        target_type="VENDOR",
        target_id=vendor.id,
        after={"project_id": project.id, "contract_id": row.contract_id},
    )
    return row


def contract_risks(db: Session, ctx: ScopeContext, warning_days: int = 45) -> list[dict]:
    """合同到期 + 已付超合同额风险。"""
    deadline = today() + timedelta(days=warning_days)
    contracts = list(
        db.execute(
            _base_query(ctx).where(Contract.status == ContractStatus.ACTIVE.value)
        )
        .scalars()
        .all()
    )
    risks: list[dict] = []
    contract_ids = [contract.id for contract in contracts]
    # 一次性聚合已付金额，避免按合同逐条查询（N+1）
    paid_map: dict[int, Decimal] = {}
    if contract_ids:
        rows = db.execute(
            select(VendorProject.contract_id, func.coalesce(func.sum(VendorProject.paid_amount), 0))
            .where(VendorProject.contract_id.in_(contract_ids))
            .group_by(VendorProject.contract_id)
        ).all()
        paid_map = {int(contract_id): Decimal(str(total or 0)) for contract_id, total in rows}
    for contract in contracts:
        if contract.end_date and contract.end_date <= deadline:
            days = (contract.end_date - today()).days
            risks.append(
                {
                    "type": "CONTRACT_EXPIRING" if days >= 0 else "CONTRACT_EXPIRED",
                    "level": "HIGH" if days < 15 else "MEDIUM",
                    "vendor_id": contract.vendor_id,
                    "contract_id": contract.id,
                    "contract_no": contract.no,
                    "message": f"合同 {contract.no} 将于 {contract.end_date} 到期（剩余 {days} 天）",
                    "days": days,
                }
            )
        paid = paid_map.get(contract.id, Decimal("0"))
        if contract.amount > 0 and paid > contract.amount:
            risks.append(
                {
                    "type": "PAYMENT_OVERRUN",
                    "level": "HIGH",
                    "vendor_id": contract.vendor_id,
                    "contract_id": contract.id,
                    "contract_no": contract.no,
                    "message": f"合同 {contract.no} 已付 {paid} 超过合同额 {contract.amount}",
                }
            )
    return risks


def mark_expired(db: Session) -> int:
    """定时任务：把已到期且仍为 ACTIVE 的合同标记 EXPIRED。"""
    rows = db.execute(
        select(Contract).where(
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.end_date.is_not(None),
            Contract.end_date < today(),
        )
    ).scalars()
    count = 0
    for contract in rows:
        contract.status = ContractStatus.EXPIRED.value
        contract.version = int(contract.version or 1) + 1
        count += 1
    if count:
        db.flush()
    return count
