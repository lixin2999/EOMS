from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.response import ok, paged
from app.api.serializers import to_dict, user_detail
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.pagination import PageParams
from app.models.iam import Dept
from app.schemas.common import (
    ConfigIn,
    CustomerIn,
    DeptIn,
    DictIn,
    ResetPasswordIn,
    RoleIn,
    UserIn,
    UserUpdateIn,
)
from app.services.iam import admin
from app.utils.datetime import to_datetime

router = APIRouter(prefix="/iam", tags=["平台管理"])


@router.get("/users", summary="用户列表", dependencies=[Depends(require_permission("system:user"))])
def list_users(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    keyword: str | None = None,
    dept_id: int | None = None,
    status: str | None = None,
) -> dict:
    result = admin.list_users(db, ctx, params, keyword=keyword, dept_id=dept_id, status=status)
    dept_names = admin.dept_name_map(db, [user.dept_id or 0 for user in result["items"]])
    return ok(
        {
            "items": [admin.serialize_user(db, user, dept_names) for user in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


@router.post("/users", summary="新建用户", dependencies=[Depends(require_permission("system:user"))])
def create_user(payload: UserIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = admin.create_user(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(admin.serialize_user(db, item), "用户已创建")


@router.get("/users/{user_id}", summary="用户详情", dependencies=[Depends(require_permission("system:user"))])
def get_user(user_id: int, db: DbSession, ctx: Scope) -> dict:
    item = admin.get_user(db, ctx, user_id)
    dept = db.get(Dept, item.dept_id) if item.dept_id else None
    data = user_detail(item, dept.name if dept else "")
    data["phone"] = admin.serialize_user(db, item)["phone"]
    return ok(data)


@router.put("/users/{user_id}", summary="更新用户", dependencies=[Depends(require_permission("system:user"))])
def update_user(user_id: int, payload: UserUpdateIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = admin.update_user(db, user, ctx, user_id, payload.model_dump(exclude_unset=True))
    return ok(admin.serialize_user(db, item), "用户已更新")


@router.post(
    "/users/{user_id}/reset-password",
    summary="重置用户密码",
    dependencies=[Depends(require_permission("system:user"))],
)
def reset_password(user_id: int, payload: ResetPasswordIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    admin.reset_user_password(db, user, ctx, user_id, payload.new_password)
    return ok(None, "密码已重置，用户下次登录需强制改密")


@router.get("/roles", summary="角色列表", dependencies=[Depends(require_permission("system:role"))])
def list_roles(db: DbSession, ctx: Scope) -> dict:
    items = []
    for role in admin.list_roles(db, ctx):
        data = to_dict(role)
        data["permission_ids"] = admin.role_permission_ids(db, role.id)
        items.append(data)
    return ok(items)


@router.post("/roles", summary="新建角色", dependencies=[Depends(require_permission("system:role"))])
def create_role(payload: RoleIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    role = admin.save_role(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(role), "角色已创建")


@router.put("/roles/{role_id}", summary="更新角色", dependencies=[Depends(require_permission("system:role"))])
def update_role(role_id: int, payload: RoleIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    role = admin.save_role(db, user, ctx, payload.model_dump(exclude_unset=True), role_id=role_id)
    return ok(to_dict(role), "角色已更新")


@router.delete("/roles/{role_id}", summary="删除角色", dependencies=[Depends(require_permission("system:role"))])
def delete_role(role_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    admin.delete_role(db, user, ctx, role_id)
    return ok(None, "角色已删除")


@router.get(
    "/permissions/tree", summary="权限点树", dependencies=[Depends(require_permission("system:role"))]
)
def permission_tree(db: DbSession) -> dict:
    return ok(admin.permission_tree(db))


@router.get("/depts/tree", summary="部门树", dependencies=[Depends(require_permission("system:dept"))])
def dept_tree(db: DbSession, ctx: Scope) -> dict:
    return ok(admin.dept_tree(db, ctx))


@router.post("/depts", summary="新建部门", dependencies=[Depends(require_permission("system:dept"))])
def create_dept(payload: DeptIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = admin.save_dept(db, user, ctx, payload.model_dump(exclude_unset=True))
    return ok(to_dict(item), "部门已创建")


@router.put("/depts/{dept_id}", summary="更新部门", dependencies=[Depends(require_permission("system:dept"))])
def update_dept(dept_id: int, payload: DeptIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = admin.save_dept(db, user, ctx, payload.model_dump(exclude_unset=True), dept_id=dept_id)
    return ok(to_dict(item), "部门已更新")


@router.get("/audit-logs", summary="审计日志", dependencies=[Depends(require_permission("system:audit"))])
def audit_logs(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    action: str | None = None,
    target_type: str | None = None,
    user_id: int | None = None,
    keyword: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    result = admin.list_audit_logs(
        db,
        ctx,
        params,
        action=action,
        target_type=target_type,
        user_id=user_id,
        keyword=keyword,
        start=to_datetime(start),
        end=to_datetime(end),
    )
    return ok(paged(result, to_dict))


@router.get("/dicts", summary="字典列表", dependencies=[Depends(require_permission("system:config"))])
def list_dicts(db: DbSession, ctx: Scope, dict_type: str | None = None) -> dict:
    return ok([to_dict(item) for item in admin.list_dicts(db, ctx, dict_type)])


@router.post("/dicts", summary="保存字典", dependencies=[Depends(require_permission("system:config"))])
def create_dict(payload: DictIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    return ok(to_dict(admin.save_dict(db, user, ctx, payload.model_dump(exclude_unset=True))), "字典已保存")


@router.put("/dicts/{dict_id}", summary="更新字典", dependencies=[Depends(require_permission("system:config"))])
def update_dict(dict_id: int, payload: DictIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    return ok(
        to_dict(admin.save_dict(db, user, ctx, payload.model_dump(exclude_unset=True), dict_id=dict_id)),
        "字典已更新",
    )


@router.delete("/dicts/{dict_id}", summary="删除字典", dependencies=[Depends(require_permission("system:config"))])
def delete_dict(dict_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    admin.delete_dict(db, user, ctx, dict_id)
    return ok(None, "字典已删除")


@router.get("/configs", summary="系统参数", dependencies=[Depends(require_permission("system:config"))])
def list_configs(db: DbSession) -> dict:
    return ok([to_dict(item) for item in admin.list_configs(db)])


@router.put("/configs/{key}", summary="设置系统参数", dependencies=[Depends(require_permission("system:config"))])
def set_config(key: str, payload: ConfigIn, db: DbSession, user: CurrentUser) -> dict:
    item = admin.set_config(db, user, key, payload.value, payload.description)
    return ok(to_dict(item), "参数已保存")


@router.get("/customers", summary="客户列表")
def list_customers(db: DbSession, ctx: Scope, keyword: str | None = None) -> dict:
    return ok([admin.serialize_customer(item) for item in admin.list_customers(db, ctx, keyword)])


@router.post("/customers", summary="新建客户", dependencies=[Depends(require_permission("project:create"))])
def create_customer(payload: CustomerIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    return ok(
        admin.serialize_customer(admin.save_customer(db, user, ctx, payload.model_dump(exclude_unset=True))),
        "客户已创建",
    )


@router.put(
    "/customers/{customer_id}",
    summary="更新客户",
    dependencies=[Depends(require_permission("project:create"))],
)
def update_customer(customer_id: int, payload: CustomerIn, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    return ok(
        admin.serialize_customer(
            admin.save_customer(db, user, ctx, payload.model_dump(exclude_unset=True), customer_id=customer_id)
        ),
        "客户已更新",
    )
