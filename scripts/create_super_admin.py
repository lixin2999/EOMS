"""幂等创建 EOMS 超级管理员。

适用于已完成 Alembic 迁移的空库和已有数据库。默认不修改已有账号密码；
只有显式传入 ``--reset-password`` 才重置。密码优先从环境变量读取，否则交互输入。

用法：
    python scripts/create_super_admin.py --company-code EOMS --company-name "示例公司" --username admin
    python scripts/create_super_admin.py --company-code EOMS --username admin --reset-password
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: E402,F401  确保全部模型注册到 Base.metadata
from app.core.cache import cache
from app.core.errors import BusinessRuleError
from app.core.security import check_password_strength, hash_password
from app.db.session import SessionLocal, session_scope
from app.models.enums import UserStatus
from app.models.iam import AuditLog, Company, Dept, Permission, Role, RolePermission, User
from app.services.iam.audit import snapshot, write_audit
from app.utils.datetime import now
from scripts import seed

_COMPANY_CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_USER_AUDIT_FIELDS = [
    "company_id",
    "dept_id",
    "username",
    "real_name",
    "email",
    "role_ids",
    "status",
    "is_super",
    "first_login",
]


@dataclass(frozen=True)
class SuperAdminResult:
    company_id: int
    user_id: int
    username: str
    company_created: bool
    department_created: bool
    user_created: bool
    user_updated: bool
    password_reset: bool


def _company_code(value: str) -> str:
    code = value.strip().upper()
    if not _COMPANY_CODE_RE.fullmatch(code):
        raise BusinessRuleError("公司编码须为 1-32 位字母、数字、下划线或连字符，且不能以连字符开头")
    return code


def _username(value: str) -> str:
    username = value.strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise BusinessRuleError("用户名须为 1-64 位字母、数字、下划线、点或连字符，且不能以标点开头")
    return username


def _validate_password(password: str, username: str) -> None:
    errors = check_password_strength(password, username=username)
    if errors:
        raise BusinessRuleError("；".join(errors))


def _require_schema(db: Session) -> None:
    required = {
        Company.__tablename__,
        Dept.__tablename__,
        User.__tablename__,
        Permission.__tablename__,
        Role.__tablename__,
        RolePermission.__tablename__,
        AuditLog.__tablename__,
    }
    available = set(inspect(db.connection()).get_table_names())
    missing = sorted(required - available)
    if missing:
        raise BusinessRuleError(f"数据库结构不完整，缺少表：{', '.join(missing)}；请先执行 alembic upgrade head")


def _ensure_builtin_roles(db: Session, permissions: dict[str, Permission]) -> dict[str, Role]:
    """补齐内置角色及缺失授权，不删除已有授权。"""
    existing = {role.code: role for role in db.execute(select(Role)).scalars().all()}
    roles: dict[str, Role] = {}
    for code, name, scope, remark in seed.ROLE_SPECS:
        role = existing.get(code)
        if role is None:
            role = Role(
                company_id=None,
                code=code,
                name=name,
                data_scope=scope,
                is_builtin=True,
                status="ACTIVE",
                remark=remark,
            )
            db.add(role)
            db.flush()
        elif role.company_id is not None:
            raise BusinessRuleError(f"角色编码 {code} 已被租户角色占用，禁止修改或提升")
        roles[code] = role
    db.flush()

    admin = roles["ADMIN"]
    if admin.status != "ACTIVE":
        raise BusinessRuleError("内置 ADMIN 角色已停用，请先检查并恢复该角色")

    all_codes = [*[item[0] for item in seed.MENUS], *[item[0] for item in seed.APIS]]
    for code, role in roles.items():
        assigned = set(
            db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).scalars()
        )
        permission_codes = all_codes if code == "ADMIN" else seed.ROLE_PERMISSIONS.get(code, [])
        for permission_code in permission_codes:
            permission = permissions.get(permission_code)
            if permission is not None and permission.id not in assigned:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
                assigned.add(permission.id)
    db.flush()
    return roles


def _ensure_company_and_department(
    db: Session,
    *,
    company_code: str,
    company_name: str | None,
    dept_code: str,
    dept_name: str,
) -> tuple[Company, Dept, bool, bool]:
    company = db.execute(select(Company).where(Company.code == company_code)).scalar_one_or_none()
    company_created = company is None
    if company is None:
        if not company_name or not company_name.strip():
            raise BusinessRuleError("创建新公司时必须提供 --company-name")
        company = Company(name=company_name.strip()[:128], code=company_code, status="ACTIVE")
        db.add(company)
        db.flush()
    elif company.status != "ACTIVE":
        raise BusinessRuleError(f"公司 {company.code} 已停用，请先恢复公司状态")

    department = db.execute(
        select(Dept)
        .where(Dept.company_id == company.id, Dept.parent_id.is_(None), Dept.code == dept_code)
        .order_by(Dept.id)
        .limit(1)
    ).scalar_one_or_none()
    department_created = department is None
    if department is None:
        department = Dept(company_id=company.id, name=dept_name.strip()[:128], code=dept_code, path="/", sort=1)
        db.add(department)
        db.flush()
        department.path = f"/{department.id}/"
        db.flush()
    return company, department, company_created, department_created


def ensure_super_admin(
    db: Session,
    *,
    company_code: str,
    username: str,
    password: str | None = None,
    reset_password: bool = False,
    company_name: str | None = None,
    real_name: str | None = None,
    email: str | None = None,
    dept_code: str = "HQ",
    dept_name: str = "总部",
) -> SuperAdminResult:
    """创建或修正目标公司超级管理员；事务提交由调用方负责。"""
    _require_schema(db)
    company_code = _company_code(company_code)
    username = _username(username)
    dept_code = dept_code.strip() or "HQ"
    dept_name = dept_name.strip() or "总部"

    company = db.execute(select(Company).where(Company.code == company_code)).scalar_one_or_none()
    if company is not None and company.status != "ACTIVE":
        raise BusinessRuleError(f"公司 {company.code} 已停用，请先恢复公司状态")
    if company is None and (not company_name or not company_name.strip()):
        raise BusinessRuleError("创建新公司时必须提供 --company-name")

    user = db.execute(select(User).where(func.lower(User.username) == username)).scalar_one_or_none()
    if user is not None and company is not None and user.company_id != company.id:
        raise BusinessRuleError("用户名已属于其他公司，禁止跨公司接管账号")
    if company is None and user is not None:
        raise BusinessRuleError("用户名已存在，禁止为新公司接管已有账号")

    needs_password = user is None or reset_password
    if needs_password:
        if password is None:
            raise BusinessRuleError("新建账号或重置密码时必须提供密码")
        _validate_password(password, username)

    permissions = seed.seed_permissions(db)
    roles = _ensure_builtin_roles(db, permissions)
    company, department, company_created, department_created = _ensure_company_and_department(
        db,
        company_code=company_code,
        company_name=company_name,
        dept_code=dept_code,
        dept_name=dept_name,
    )

    before = snapshot(user, _USER_AUDIT_FIELDS) if user else {}
    user_created = user is None
    password_reset = bool(reset_password)
    if user is None:
        user = User(
            company_id=company.id,
            dept_id=department.id,
            username=username,
            password_hash=hash_password(password or "", username=username),
            real_name=(real_name or username).strip()[:64],
            email=(email or "").strip()[:128] or None,
            role_ids=[roles["ADMIN"].id],
            status=UserStatus.ACTIVE.value,
            is_super=True,
            first_login=False,
            password_updated_at=now(),
        )
        db.add(user)
        db.flush()
    else:
        role_ids = list(user.role_ids or [])
        updated = False
        if roles["ADMIN"].id not in role_ids:
            role_ids.append(roles["ADMIN"].id)
            updated = True
        if not user.is_super:
            user.is_super = True
            updated = True
        if user.status != UserStatus.ACTIVE.value:
            user.status = UserStatus.ACTIVE.value
            updated = True
        if user.first_login:
            user.first_login = False
            updated = True
        if user.dept_id is None:
            user.dept_id = department.id
            updated = True
        if reset_password:
            user.password_hash = hash_password(password or "", username=user.username)
            user.password_updated_at = now()
            updated = True
        if updated:
            user.role_ids = role_ids
            user.version = int(user.version or 1) + 1
            db.flush()

    user_updated = not user_created and snapshot(user, _USER_AUDIT_FIELDS) != before
    if user_created or user_updated or password_reset:
        action = "CREATE_SUPER_ADMIN" if user_created else (
            "RESET_SUPER_ADMIN_PASSWORD" if password_reset else "ENSURE_SUPER_ADMIN"
        )
        write_audit(
            db,
            user=user,
            action=action,
            target_type="USER",
            target_id=user.id,
            before=before,
            after=snapshot(user, _USER_AUDIT_FIELDS),
            company_id=company.id,
        )
    return SuperAdminResult(
        company_id=company.id,
        user_id=user.id,
        username=user.username,
        company_created=company_created,
        department_created=department_created,
        user_created=user_created,
        user_updated=user_updated,
        password_reset=password_reset,
    )


def _read_password(env_name: str, username: str) -> str:
    value = os.environ.get(env_name)
    if value:
        _validate_password(value, username)
        return value
    if not sys.stdin.isatty():
        raise BusinessRuleError(f"非交互环境请在环境变量 {env_name} 中提供密码")
    password = getpass.getpass("请输入超级管理员密码：")
    confirmation = getpass.getpass("请再次输入密码：")
    if password != confirmation:
        raise BusinessRuleError("两次输入的密码不一致")
    _validate_password(password, username)
    return password


def _clear_runtime_state(result: SuperAdminResult) -> None:
    cache.delete_prefix("perm:")
    cache.delete(
        f"sess:{result.user_id}",
        f"lock:sess:{result.user_id}",
        f"login:fail:{result.username.lower()}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="幂等创建 EOMS 超级管理员（默认不重置已有密码）")
    parser.add_argument("--company-code", required=True, help="公司编码，如 EOMS")
    parser.add_argument("--company-name", help="公司名称；创建新公司时必填")
    parser.add_argument("--username", default="admin", help="登录用户名，默认 admin")
    parser.add_argument("--real-name", help="姓名；新建账号时可选")
    parser.add_argument("--email", help="邮箱；新建账号时可选")
    parser.add_argument("--dept-code", default="HQ", help="根部门编码，默认 HQ")
    parser.add_argument("--dept-name", default="总部", help="根部门名称，默认 总部")
    parser.add_argument("--reset-password", action="store_true", help="重置已有账号密码并使其会话失效")
    parser.add_argument(
        "--password-env", default="EOMS_ADMIN_PASSWORD", help="密码环境变量名，默认 EOMS_ADMIN_PASSWORD"
    )
    args = parser.parse_args()

    try:
        company_code = _company_code(args.company_code)
        username = _username(args.username)
        with SessionLocal() as db:
            _require_schema(db)
            company = db.execute(select(Company).where(Company.code == company_code)).scalar_one_or_none()
            existing = db.execute(select(User).where(func.lower(User.username) == username)).scalar_one_or_none()
        if existing is not None and (company is None or existing.company_id != company.id):
            raise BusinessRuleError("用户名已存在且不属于目标公司，禁止跨公司接管账号")
        password = _read_password(args.password_env, username) if existing is None or args.reset_password else None

        with session_scope() as db:
            result = ensure_super_admin(
                db,
                company_code=company_code,
                company_name=args.company_name,
                username=username,
                password=password,
                reset_password=args.reset_password,
                real_name=args.real_name,
                email=args.email,
                dept_code=args.dept_code,
                dept_name=args.dept_name,
            )
        _clear_runtime_state(result)
    except (BusinessRuleError, ValueError) as exc:
        raise SystemExit(f"[create-super-admin] {exc}") from exc

    print(f"[create-super-admin] 公司：{company_code}（ID={result.company_id}）")
    print(f"[create-super-admin] 超级管理员：{result.username}（ID={result.user_id}）")
    if result.company_created:
        print("[create-super-admin] 已创建公司")
    if result.department_created:
        print("[create-super-admin] 已创建根部门")
    if result.user_created:
        print("[create-super-admin] 已创建账号，密码已按当前用户名完成哈希")
    elif result.password_reset:
        print("[create-super-admin] 已重置密码，旧会话已失效")
    elif result.user_updated:
        print("[create-super-admin] 已补齐超级管理员标志、状态和 ADMIN 角色，原密码未修改")
    else:
        print("[create-super-admin] 账号已符合要求，本次未修改用户数据")
    print("[create-super-admin] 权限、内置角色及缺失授权已幂等补齐；密码不会输出到终端或日志")


if __name__ == "__main__":
    main()
