from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.models.enums import DataScope
from app.models.iam import Dept, Permission, Role, RolePermission, User
from app.models.project import Project, ProjectMember

PERM_CACHE_TTL = 300


@dataclass
class ScopeContext:
    user_id: int
    company_id: int
    dept_id: int | None
    is_super: bool = False
    scopes: set[str] = field(default_factory=set)
    dept_ids: list[int] = field(default_factory=list)
    project_ids: list[int] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    role_ids: list[int] = field(default_factory=list)

    @property
    def has_all(self) -> bool:
        return self.is_super or DataScope.ALL.value in self.scopes or DataScope.COMPANY.value in self.scopes

    def has_perm(self, code: str) -> bool:
        return self.is_super or code in self.permissions

    def has_any(self, *codes: str) -> bool:
        return self.is_super or any(code in self.permissions for code in codes)


def invalidate_permission_cache(user_id: int | None = None) -> None:
    if user_id is None:
        cache.delete_prefix("perm:")
    else:
        cache.delete(f"perm:{user_id}")


def load_permission_codes(db: Session, user: User) -> set[str]:
    if user.is_super:
        return {"*"}
    cached = cache.get_json(f"perm:{user.id}")
    if isinstance(cached, list):
        return set(cached)
    role_ids = [rid for rid in (user.role_ids or []) if isinstance(rid, int)]
    if not role_ids:
        return set()
    rows = db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    ).scalars()
    codes = {code for code in rows if code}
    cache.set_json(f"perm:{user.id}", sorted(codes), PERM_CACHE_TTL)
    return codes


def get_valid_roles(db: Session, user: User) -> list[Role]:
    role_ids = [rid for rid in (user.role_ids or []) if isinstance(rid, int)]
    if not role_ids:
        return []
    roles = db.execute(select(Role).where(Role.id.in_(role_ids), Role.status == "ACTIVE")).scalars().all()
    return [role for role in roles if role.company_id in (None, user.company_id)]


def build_scope(db: Session, user: User) -> ScopeContext:
    roles = get_valid_roles(db, user)
    scopes = {role.data_scope for role in roles if role.data_scope}
    if user.is_super:
        scopes.add(DataScope.ALL.value)
    if not scopes:
        scopes.add(DataScope.SELF.value)

    dept_ids: set[int] = set()
    if user.dept_id:
        dept_ids.add(user.dept_id)
    if DataScope.DEPT_TREE.value in scopes and user.dept_id:
        dept = db.get(Dept, user.dept_id)
        if dept:
            prefix = dept.path or f"/{dept.id}/"
            children = db.execute(
                select(Dept.id).where(
                    Dept.company_id == user.company_id,
                    Dept.path.like(f"{prefix}%"),
                )
            ).scalars()
            dept_ids.update(int(item) for item in children)

    project_ids: set[int] = set()
    if DataScope.PROJECT.value in scopes or not scopes.issubset({DataScope.SELF.value}):
        managed = db.execute(
            select(Project.id).where(Project.company_id == user.company_id, Project.manager_id == user.id)
        ).scalars()
        project_ids.update(int(item) for item in managed)
        joined = db.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.company_id == user.company_id, ProjectMember.user_id == user.id
            )
        ).scalars()
        project_ids.update(int(item) for item in joined)

    permissions = load_permission_codes(db, user)
    return ScopeContext(
        user_id=user.id,
        company_id=user.company_id,
        dept_id=user.dept_id,
        is_super=user.is_super,
        scopes=scopes,
        dept_ids=sorted(dept_ids),
        project_ids=sorted(project_ids),
        permissions=permissions,
        role_ids=list(user.role_ids or []),
    )


def scope_condition(
    ctx: ScopeContext,
    model: Any,
    *,
    dept_attr: str | None = "dept_id",
    project_attr: str | None = "project_id",
    creator_attr: str | None = "creator_id",
):
    """按数据域生成 WHERE 条件；多角色权限取并集，公司边界始终收敛。"""
    clauses = []
    company_col = getattr(model, "company_id", None)
    if company_col is not None and not ctx.is_super:
        clauses.append(company_col == ctx.company_id)

    dept_col = getattr(model, dept_attr, None) if dept_attr else None
    project_col = getattr(model, project_attr, None) if project_attr else None
    creator_col = getattr(model, creator_attr, None) if creator_attr else None

    branches: list[Any] = []
    if ctx.is_super or DataScope.ALL.value in ctx.scopes or DataScope.COMPANY.value in ctx.scopes:
        branches.append(None)  # 全公司
    if DataScope.DEPT.value in ctx.scopes and dept_col is not None and ctx.dept_id:
        branches.append(dept_col == ctx.dept_id)
    if DataScope.DEPT_TREE.value in ctx.scopes and dept_col is not None and ctx.dept_ids:
        branches.append(dept_col.in_(ctx.dept_ids))
    if DataScope.PROJECT.value in ctx.scopes and project_col is not None and ctx.project_ids:
        branches.append(project_col.in_(ctx.project_ids))
    if DataScope.SELF.value in ctx.scopes and creator_col is not None:
        branches.append(creator_col == ctx.user_id)

    if branches:
        if any(branch is None for branch in branches):
            pass  # 无附加限制
        else:
            clauses.append(or_(*branches))
    elif creator_col is not None:
        clauses.append(creator_col == ctx.user_id)

    return and_(*clauses) if clauses else None


def apply_scope(
    stmt: Select,
    ctx: ScopeContext,
    model: Any,
    **kwargs,
) -> Select:
    condition = scope_condition(ctx, model, **kwargs)
    return stmt.where(condition) if condition is not None else stmt


def get_scoped(
    db: Session,
    model: Any,
    obj_id: int,
    ctx: ScopeContext,
    **kwargs,
) -> Any:
    stmt = apply_scope(select(model).where(model.id == obj_id), ctx, model, **kwargs)
    obj = db.execute(stmt).scalar_one_or_none()
    if obj is None:
        raise NotFoundError("资源不存在或无权访问")
    return obj


def ensure_company(obj: Any, ctx: ScopeContext) -> None:
    company_id = getattr(obj, "company_id", None)
    if company_id is not None and company_id != ctx.company_id and not ctx.is_super:
        raise NotFoundError("资源不存在或无权访问")


def ensure_visible(db: Session, model: Any, obj_id: int, ctx: ScopeContext, **kwargs) -> Any:
    return get_scoped(db, model, obj_id, ctx, **kwargs)


def can_access_project(db: Session, ctx: ScopeContext, project_id: int) -> bool:
    if ctx.is_super or ctx.has_all or project_id in ctx.project_ids:
        return True
    stmt = apply_scope(select(Project.id).where(Project.id == project_id), ctx, Project, project_attr="id")
    return db.execute(stmt).scalar_one_or_none() is not None


def assert_project_access(db: Session, ctx: ScopeContext, project_id: int) -> None:
    if not can_access_project(db, ctx, project_id):
        raise ForbiddenError("无权访问该项目数据")


def apply_rls(db: Session, ctx: ScopeContext) -> None:
    """PostgreSQL 行级安全兜底：设置会话级 GUC（事务内生效）。"""
    if not (settings.rls_enabled and settings.is_postgres):
        return
    from sqlalchemy import text

    values = {
        "app.company_id": str(ctx.company_id),
        "app.user_id": str(ctx.user_id),
        "app.scope_all": "1" if ctx.has_all else "0",
        "app.dept_ids": ",".join(str(item) for item in ctx.dept_ids),
        "app.project_ids": ",".join(str(item) for item in ctx.project_ids),
        "app.bypass": "on" if ctx.is_super else "off",
    }
    for key, value in values.items():
        db.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})


def visible_menu_tree(db: Session, ctx: ScopeContext) -> list[dict]:
    stmt = select(Permission).where(Permission.type == "menu", Permission.visible.is_(True)).order_by(Permission.sort)
    menus = db.execute(stmt).scalars().all()
    allowed = [menu for menu in menus if ctx.is_super or menu.code in ctx.permissions]
    allowed_ids = {menu.id for menu in allowed}
    nodes: dict[int, dict] = {
        menu.id: {
            "id": menu.id,
            "code": menu.code,
            "name": menu.name,
            "path": menu.path,
            "component": menu.component,
            "icon": menu.icon,
            "sort": menu.sort,
            "parent_id": menu.parent_id,
            "children": [],
        }
        for menu in allowed
    }
    roots: list[dict] = []
    for menu in allowed:
        node = nodes[menu.id]
        parent = nodes.get(menu.parent_id or -1)
        if parent and (menu.parent_id in allowed_ids):
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots
