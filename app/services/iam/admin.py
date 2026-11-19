"""IAM 管理：用户、角色、权限、部门、字典、参数、客户主档、审计查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, invalidate_permission_cache
from app.core.security import check_password_strength, encrypt_text, hash_password, mask_phone
from app.models.enums import UserStatus
from app.models.iam import AuditLog, Dept, Permission, Role, RolePermission, SysConfig, SysDict, User
from app.models.platform import Customer
from app.services.iam.audit import snapshot, write_audit
from app.utils.datetime import now


# ------------------------------------------------------------------ 用户
def list_users(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    keyword: str | None = None,
    dept_id: int | None = None,
    status: str | None = None,
) -> dict:
    stmt = select(User).where(User.company_id == ctx.company_id)
    if keyword:
        stmt = stmt.where(or_(User.username.like(f"%{keyword}%"), User.real_name.like(f"%{keyword}%")))
    if dept_id:
        stmt = stmt.where(User.dept_id == dept_id)
    if status:
        stmt = stmt.where(User.status == status)
    stmt = stmt.order_by(User.id)
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_user(db: Session, ctx: ScopeContext, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or (user.company_id != ctx.company_id and not ctx.is_super):
        raise NotFoundError("用户不存在")
    return user


def _check_roles(db: Session, company_id: int, role_ids: list[int]) -> list[int]:
    ids = sorted({int(item) for item in role_ids or []})
    if not ids:
        return []
    roles = list(db.execute(select(Role).where(Role.id.in_(ids), Role.status == "ACTIVE")).scalars().all())
    if len(roles) != len(ids):
        raise BusinessRuleError("角色不存在或已停用")
    for role in roles:
        if role.company_id not in (None, company_id):
            raise BusinessRuleError("不能分配其他公司的角色")
    return ids


def create_user(db: Session, operator: User, ctx: ScopeContext, payload: dict[str, Any]) -> User:
    username = str(payload.get("username") or "").strip().lower()
    if not username:
        raise BusinessRuleError("用户名不能为空")
    if not username.replace("_", "").replace(".", "").isalnum():
        raise BusinessRuleError("用户名只能包含字母、数字、下划线和点")
    if db.execute(select(User.id).where(func.lower(User.username) == username)).first():
        raise ConflictError("用户名已存在")
    password = str(payload.get("password") or "")
    errors = check_password_strength(password, username=username)
    if errors:
        raise BusinessRuleError("；".join(errors))
    dept_id = payload.get("dept_id")
    if dept_id:
        dept = db.get(Dept, int(dept_id))
        if dept is None or dept.company_id != operator.company_id:
            raise BusinessRuleError("部门不存在")
    role_ids = _check_roles(db, operator.company_id, payload.get("role_ids") or [])
    user = User(
        company_id=operator.company_id,
        dept_id=int(dept_id) if dept_id else None,
        username=username,
        password_hash=hash_password(password, username=username),
        real_name=str(payload.get("real_name") or username)[:64],
        position=(payload.get("position") or "")[:64] or None,
        phone_enc=encrypt_text(str(payload.get("phone") or "")) or None,
        email=(payload.get("email") or "")[:128] or None,
        role_ids=role_ids,
        status=str(payload.get("status") or UserStatus.ACTIVE.value),
        first_login=bool(payload.get("first_login", True)),
        password_updated_at=now(),
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        user=operator,
        action="CREATE_USER",
        target_type="USER",
        target_id=user.id,
        after={"username": user.username, "role_ids": role_ids},
    )
    return user


def update_user(db: Session, operator: User, ctx: ScopeContext, user_id: int, payload: dict[str, Any]) -> User:
    user = get_user(db, ctx, user_id)
    expected = payload.get("version")
    if expected is not None and int(expected) != user.version:
        raise ConflictError("用户信息已被修改，请刷新后重试")
    before = snapshot(user, ["real_name", "dept_id", "position", "email", "role_ids", "status"])
    if payload.get("real_name") is not None and str(payload["real_name"]).strip():
        user.real_name = str(payload["real_name"]).strip()[:64]
    if payload.get("dept_id") is not None:
        dept_id = payload["dept_id"]
        if dept_id:
            dept = db.get(Dept, int(dept_id))
            if dept is None or dept.company_id != operator.company_id:
                raise BusinessRuleError("部门不存在")
            user.dept_id = dept.id
        else:
            user.dept_id = None
    if payload.get("position") is not None:
        user.position = (payload["position"] or "")[:64] or None
    if payload.get("email") is not None:
        user.email = (payload["email"] or "")[:128] or None
    if payload.get("phone") is not None:
        user.phone_enc = encrypt_text(str(payload["phone"] or "")) or None
    if payload.get("role_ids") is not None:
        user.role_ids = _check_roles(db, user.company_id, payload["role_ids"])
        invalidate_permission_cache(user.id)
    if payload.get("status") is not None:
        status = str(payload["status"])
        if status not in {item.value for item in UserStatus}:
            raise BusinessRuleError("用户状态非法")
        if user.id == operator.id and status != UserStatus.ACTIVE.value:
            raise BusinessRuleError("不能停用当前登录账号")
        user.status = status
    user.version = int(user.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=operator,
        action="UPDATE_USER",
        target_type="USER",
        target_id=user.id,
        before=before,
        after=snapshot(user, ["real_name", "dept_id", "position", "email", "role_ids", "status"]),
    )
    return user


def reset_user_password(db: Session, operator: User, ctx: ScopeContext, user_id: int, new_password: str) -> None:
    from app.services.iam.auth import reset_password

    target = get_user(db, ctx, user_id)
    reset_password(db, operator, target, new_password, force_change=True)


# ------------------------------------------------------------------ 角色 / 权限
def list_roles(db: Session, ctx: ScopeContext) -> list[Role]:
    return list(
        db.execute(
            select(Role).where(or_(Role.company_id.is_(None), Role.company_id == ctx.company_id)).order_by(Role.id)
        )
        .scalars()
        .all()
    )


def role_permission_ids(db: Session, role_id: int) -> list[int]:
    return [
        int(item)
        for item in db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role_id)).scalars()
    ]


def save_role(
    db: Session, operator: User, ctx: ScopeContext, payload: dict[str, Any], role_id: int | None = None
) -> Role:
    code = str(payload.get("code") or "").strip().upper()
    name = str(payload.get("name") or "").strip()
    if not code or not name:
        raise BusinessRuleError("角色编码与名称不能为空")
    data_scope = str(payload.get("data_scope") or "SELF")
    if data_scope not in {"ALL", "COMPANY", "DEPT", "DEPT_TREE", "PROJECT", "SELF"}:
        raise BusinessRuleError("数据域非法")
    if role_id:
        role = db.get(Role, role_id)
        if role is None or (role.company_id not in (None, ctx.company_id) and not ctx.is_super):
            raise NotFoundError("角色不存在")
        if role.is_builtin and not operator.is_super:
            raise BusinessRuleError("内置角色仅超级管理员可修改")
        if role.code != code and db.execute(select(Role.id).where(Role.code == code)).first():
            raise ConflictError("角色编码已存在")
        before = snapshot(role)
        role.code = code
        role.name = name[:64]
        role.data_scope = data_scope
        role.remark = (payload.get("remark") or "")[:255] or None
        if "status" in payload:
            role.status = str(payload["status"])
        db.flush()
    else:
        if db.execute(select(Role.id).where(Role.code == code)).first():
            raise ConflictError("角色编码已存在")
        role = Role(
            company_id=ctx.company_id,
            code=code,
            name=name[:64],
            data_scope=data_scope,
            is_builtin=False,
            status="ACTIVE",
            remark=(payload.get("remark") or "")[:255] or None,
        )
        db.add(role)
        db.flush()
        before = None
    if payload.get("permission_ids") is not None:
        ids = sorted({int(item) for item in payload["permission_ids"]})
        if ids:
            found = set(db.execute(select(Permission.id).where(Permission.id.in_(ids))).scalars())
            if len(found) != len(ids):
                raise BusinessRuleError("权限点不存在")
        db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for permission_id in ids:
            db.add(RolePermission(role_id=role.id, permission_id=permission_id))
        db.flush()
        invalidate_permission_cache()
    write_audit(
        db,
        user=operator,
        action="UPDATE_ROLE" if role_id else "CREATE_ROLE",
        target_type="ROLE",
        target_id=role.id,
        before=before,
        after=snapshot(role),
    )
    return role


def delete_role(db: Session, operator: User, ctx: ScopeContext, role_id: int) -> None:
    role = db.get(Role, role_id)
    if role is None or (role.company_id not in (None, ctx.company_id) and not ctx.is_super):
        raise NotFoundError("角色不存在")
    if role.is_builtin:
        raise BusinessRuleError("内置角色不能删除")
    used = db.execute(select(User.id).where(User.company_id == ctx.company_id)).scalars()
    for user_id in used:
        owner = db.get(User, user_id)
        if owner is not None and role.id in (owner.role_ids or []):
            raise BusinessRuleError("角色已被用户使用，不能删除")
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    db.delete(role)
    db.flush()
    invalidate_permission_cache()
    write_audit(db, user=operator, action="DELETE_ROLE", target_type="ROLE", target_id=role_id)


def list_permissions(db: Session) -> list[Permission]:
    return list(db.execute(select(Permission).order_by(Permission.sort, Permission.id)).scalars().all())


def permission_tree(db: Session) -> list[dict]:
    rows = list_permissions(db)
    nodes: dict[int, dict[str, Any]] = {
        item.id: {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "type": item.type,
            "parent_id": item.parent_id,
            "path": item.path,
            "sort": item.sort,
            "children": [],
        }
        for item in rows
    }
    roots: list[dict] = []
    for item in rows:
        node = nodes[item.id]
        parent = nodes.get(item.parent_id or -1)
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


# ------------------------------------------------------------------ 部门
def dept_tree(db: Session, ctx: ScopeContext) -> list[dict]:
    rows = list(
        db.execute(select(Dept).where(Dept.company_id == ctx.company_id).order_by(Dept.sort, Dept.id)).scalars().all()
    )
    nodes: dict[int, dict[str, Any]] = {
        item.id: {
            "id": item.id,
            "name": item.name,
            "code": item.code,
            "parent_id": item.parent_id,
            "leader_user_id": item.leader_user_id,
            "sort": item.sort,
            "status": item.status,
            "path": item.path,
            "children": [],
        }
        for item in rows
    }
    roots: list[dict] = []
    for item in rows:
        node = nodes[item.id]
        parent = nodes.get(item.parent_id or -1)
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def save_dept(
    db: Session, operator: User, ctx: ScopeContext, payload: dict[str, Any], dept_id: int | None = None
) -> Dept:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("部门名称不能为空")
    parent_id = payload.get("parent_id")
    parent = None
    if parent_id:
        parent = db.get(Dept, int(parent_id))
        if parent is None or parent.company_id != ctx.company_id:
            raise BusinessRuleError("上级部门不存在")
    leader_id = payload.get("leader_user_id")
    if leader_id:
        leader = db.get(User, int(leader_id))
        if leader is None or leader.company_id != ctx.company_id:
            raise BusinessRuleError("部门负责人不存在")
    if dept_id:
        dept = db.get(Dept, dept_id)
        if dept is None or dept.company_id != ctx.company_id:
            raise NotFoundError("部门不存在")
        if parent and parent.id == dept.id:
            raise BusinessRuleError("上级部门不能是自己")
        if parent and (parent.path or "").startswith(dept.path or ""):
            raise BusinessRuleError("不能移动到自己的下级部门")
        before = snapshot(dept)
        dept.name = name[:128]
        dept.code = (payload.get("code") or "")[:64] or None
        dept.parent_id = parent.id if parent else None
        dept.leader_user_id = int(leader_id) if leader_id else None
        dept.sort = int(payload.get("sort") or 0)
        if "status" in payload:
            dept.status = str(payload["status"])
        dept.path = f"{parent.path.rstrip('/')}/{dept.id}/" if parent else f"/{dept.id}/"
        db.flush()
        _fix_children_path(db, dept)
        write_audit(
            db,
            user=operator,
            action="UPDATE_DEPT",
            target_type="DEPT",
            target_id=dept.id,
            before=before,
            after=snapshot(dept),
        )
        return dept
    dept = Dept(
        company_id=ctx.company_id,
        parent_id=parent.id if parent else None,
        name=name[:128],
        code=(payload.get("code") or "")[:64] or None,
        leader_user_id=int(leader_id) if leader_id else None,
        sort=int(payload.get("sort") or 0),
        status="ACTIVE",
        path="/",
    )
    db.add(dept)
    db.flush()
    dept.path = f"{parent.path.rstrip('/')}/{dept.id}/" if parent else f"/{dept.id}/"
    db.flush()
    write_audit(db, user=operator, action="CREATE_DEPT", target_type="DEPT", target_id=dept.id, after=snapshot(dept))
    return dept


def _fix_children_path(db: Session, dept: Dept) -> None:
    children = list(db.execute(select(Dept).where(Dept.parent_id == dept.id)).scalars().all())
    for child in children:
        child.path = f"{dept.path.rstrip('/')}/{child.id}/"
        db.flush()
        _fix_children_path(db, child)


# ------------------------------------------------------------------ 审计 / 字典 / 参数
def list_audit_logs(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    action: str | None = None,
    target_type: str | None = None,
    user_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = select(AuditLog).where(or_(AuditLog.company_id == ctx.company_id, AuditLog.company_id.is_(None)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if start:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end:
        stmt = stmt.where(AuditLog.created_at <= end)
    if keyword:
        stmt = stmt.where(or_(AuditLog.action.like(f"%{keyword}%"), AuditLog.username.like(f"%{keyword}%")))
    stmt = stmt.order_by(AuditLog.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def list_dicts(db: Session, ctx: ScopeContext, dict_type: str | None = None) -> list[SysDict]:
    stmt = select(SysDict).where(or_(SysDict.company_id.is_(None), SysDict.company_id == ctx.company_id))
    if dict_type:
        stmt = stmt.where(SysDict.dict_type == dict_type)
    return list(db.execute(stmt.order_by(SysDict.dict_type, SysDict.sort, SysDict.id)).scalars().all())


def save_dict(
    db: Session, operator: User, ctx: ScopeContext, payload: dict[str, Any], dict_id: int | None = None
) -> SysDict:
    dict_type = str(payload.get("dict_type") or "").strip()
    label = str(payload.get("label") or "").strip()
    value = str(payload.get("value") or "").strip()
    if not dict_type or not label or not value:
        raise BusinessRuleError("字典类型、标签、值不能为空")
    if dict_id:
        item = db.get(SysDict, dict_id)
        if item is None or item.company_id != ctx.company_id:
            raise NotFoundError("字典项不存在")
        item.dict_type = dict_type
        item.label = label[:128]
        item.value = value[:128]
        item.sort = int(payload.get("sort") or 0)
        item.status = str(payload.get("status") or "ACTIVE")
        item.remark = (payload.get("remark") or "")[:255] or None
    else:
        item = SysDict(
            company_id=ctx.company_id,
            dict_type=dict_type[:64],
            label=label[:128],
            value=value[:128],
            sort=int(payload.get("sort") or 0),
            status=str(payload.get("status") or "ACTIVE"),
            remark=(payload.get("remark") or "")[:255] or None,
        )
        db.add(item)
    db.flush()
    write_audit(db, user=operator, action="SAVE_DICT", target_type="DICT", target_id=item.id)
    return item


def delete_dict(db: Session, operator: User, ctx: ScopeContext, dict_id: int) -> None:
    item = db.get(SysDict, dict_id)
    if item is None or item.company_id != ctx.company_id:
        raise NotFoundError("字典项不存在")
    db.delete(item)
    db.flush()
    write_audit(db, user=operator, action="DELETE_DICT", target_type="DICT", target_id=dict_id)


def list_configs(db: Session) -> list[SysConfig]:
    return list(db.execute(select(SysConfig).order_by(SysConfig.key)).scalars().all())


def set_config(db: Session, operator: User, key: str, value: Any, description: str | None = None) -> SysConfig:
    key = (key or "").strip()
    if not key:
        raise BusinessRuleError("配置键不能为空")
    item = db.execute(select(SysConfig).where(SysConfig.key == key)).scalar_one_or_none()
    if item is None:
        item = SysConfig(key=key, value=value, description=description, updated_by=operator.id)
        db.add(item)
    else:
        item.value = value
        if description:
            item.description = description[:255]
        item.updated_by = operator.id
    db.flush()
    write_audit(db, user=operator, action="SET_CONFIG", target_type="CONFIG", target_id=key, after={"value": value})
    return item


# ------------------------------------------------------------------ 客户
def list_customers(db: Session, ctx: ScopeContext, keyword: str | None = None) -> list[Customer]:
    stmt = select(Customer).where(Customer.company_id == ctx.company_id)
    if keyword:
        stmt = stmt.where(Customer.name.like(f"%{keyword}%"))
    return list(db.execute(stmt.order_by(Customer.id.desc())).scalars().all())


def save_customer(
    db: Session, operator: User, ctx: ScopeContext, payload: dict[str, Any], customer_id: int | None = None
) -> Customer:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise BusinessRuleError("客户名称不能为空")
    if customer_id:
        item = db.get(Customer, customer_id)
        if item is None or item.company_id != ctx.company_id:
            raise NotFoundError("客户不存在")
    else:
        exists = db.execute(
            select(Customer.id).where(Customer.company_id == ctx.company_id, Customer.name == name)
        ).first()
        if exists:
            raise ConflictError("客户名称已存在")
        item = Customer(company_id=ctx.company_id, name=name[:128], creator_id=operator.id)
        db.add(item)
    item.name = name[:128]
    item.code = (payload.get("code") or "")[:64] or None
    item.contact = (payload.get("contact") or "")[:64] or None
    if payload.get("phone") is not None:
        item.phone_enc = encrypt_text(str(payload["phone"])) or None
    item.email = (payload.get("email") or "")[:128] or None
    item.address = (payload.get("address") or "")[:255] or None
    item.status = str(payload.get("status") or "ACTIVE")
    db.flush()
    write_audit(db, user=operator, action="SAVE_CUSTOMER", target_type="CUSTOMER", target_id=item.id)
    return item


def serialize_customer(customer: Customer) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "code": customer.code,
        "contact": customer.contact,
        "phone": mask_phone(_safe_decrypt(customer.phone_enc)),
        "email": customer.email,
        "address": customer.address,
        "status": customer.status,
        "created_at": customer.created_at,
    }


def serialize_user(db: Session, user: User) -> dict:
    dept = db.get(Dept, user.dept_id) if user.dept_id else None
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "dept_id": user.dept_id,
        "dept_name": dept.name if dept else "",
        "position": user.position,
        "phone": mask_phone(_safe_decrypt(user.phone_enc)),
        "email": user.email,
        "role_ids": user.role_ids or [],
        "status": user.status,
        "is_super": user.is_super,
        "first_login": user.first_login,
        "last_login_at": user.last_login_at,
        "version": user.version,
        "created_at": user.created_at,
    }


def _safe_decrypt(value: str | None) -> str:
    from app.core.security import decrypt_text

    try:
        return decrypt_text(value)
    except ValueError:
        return ""
