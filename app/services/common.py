from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.models.iam import Company, Role, SysFile, User


def company_code(db: Session, company_id: int) -> str:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("公司不存在")
    return company.code


def users_by_role(db: Session, company_id: int, role_code: str) -> list[User]:
    role = db.execute(
        select(Role).where(Role.code == role_code, Role.status == "ACTIVE").order_by(Role.company_id.is_(None))
    ).scalars().first()
    if role is None:
        return []
    users = db.execute(
        select(User).where(User.company_id == company_id, User.status == "ACTIVE")
    ).scalars()
    return [user for user in users if role.id in (user.role_ids or [])]


def ensure_choice(value: str | None, allowed: set[str], field_name: str, *, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            raise BusinessRuleError(f"{field_name}不能为空")
        return ""
    if value not in allowed:
        raise BusinessRuleError(f"{field_name}取值非法")
    return value


def ensure_files(db: Session, file_ids: list[int] | None, company_id: int) -> list[int]:
    ids = [int(item) for item in (file_ids or []) if str(item).isdigit()]
    if not ids:
        return []
    found = set(
        db.execute(
            select(SysFile.id).where(SysFile.id.in_(ids), SysFile.company_id == company_id)
        ).scalars()
    )
    missing = [item for item in ids if item not in found]
    if missing:
        raise BusinessRuleError("附件不存在或不属于当前公司")
    return ids


def serialize_page(result: dict[str, Any], serializer) -> dict[str, Any]:
    return {
        "items": [serializer(item) for item in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }
