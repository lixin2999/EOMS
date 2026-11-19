from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
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


def claim_version(
    db: Session,
    model: Any,
    obj: Any,
    *,
    allowed_status: set[str] | None = None,
) -> None:
    """原子抢占业务单据（乐观锁）。

    以 ``UPDATE ... WHERE version = 当前版本`` 抢占，SQLite 与 PostgreSQL 都能
    阻止并发重复提交；失败即说明已被其他请求处理，直接返回 409。
    """
    current = int(getattr(obj, "version", 1) or 1)
    stmt = (
        update(model)
        .where(model.id == obj.id, model.version == current)
        .values(version=current + 1)
        .execution_options(synchronize_session=False)
    )
    if allowed_status is not None:
        stmt = stmt.where(model.status.in_(allowed_status))
    result = db.execute(stmt)
    # 仅 UPDATE/DELETE 返回 CursorResult；通用 Result 未声明 rowcount，故按属性取。
    if int(getattr(result, "rowcount", 0)) != 1:
        raise ConflictError("单据状态已变化，请刷新后重试")
    obj.version = current + 1
