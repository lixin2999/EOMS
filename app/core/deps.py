from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.scope import ScopeContext, apply_rls, build_scope
from app.core.security import decode_token
from app.db.session import get_db as _get_db
from app.models.iam import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer Token")


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


DbSession = Annotated[Session, Depends(get_db)]


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else ""


def get_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:255]


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("请先登录")
    payload = decode_token(credentials.credentials, "access")
    jti = str(payload.get("jti") or "")
    if cache.get(f"bl:access:{jti}"):
        raise UnauthorizedError("登录状态已注销")
    try:
        user_id = int(payload.get("sub", "0"))
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("身份凭证无效") from exc
    user = db.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise UnauthorizedError("账号不存在或已被停用")
    if not user.is_super and int(payload.get("company_id", 0)) != user.company_id:
        raise UnauthorizedError("身份凭证与账号不匹配")
    password_ts = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0
    if int(payload.get("pwd", 0)) != password_ts:
        raise UnauthorizedError("密码已变更，请重新登录")
    if user.first_login:
        allowed = {
            f"{settings.api_prefix}/auth/password",
            f"{settings.api_prefix}/auth/logout",
            f"{settings.api_prefix}/auth/me",
        }
        if request.url.path not in allowed:
            from app.core.errors import AppError, ErrorCode

            raise AppError("首次登录请先修改密码", ErrorCode.BUSINESS_RULE, 403)
    request.state.user = user
    request.state.jti = jti
    request.state.token_payload = payload
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_scope(request: Request, db: DbSession, user: CurrentUser) -> ScopeContext:
    if getattr(request.state, "scope", None) is not None:
        return request.state.scope
    scope = build_scope(db, user)
    apply_rls(db, scope)
    request.state.scope = scope
    return scope


Scope = Annotated[ScopeContext, Depends(get_scope)]


def require_permission(*codes: str, all_required: bool = False) -> Callable:
    """权限点校验（菜单/接口/按钮）：不依赖前端隐藏。"""

    def dependency(scope: Scope) -> ScopeContext:
        if scope.is_super:
            return scope
        if all_required:
            missing = [code for code in codes if code not in scope.permissions]
            if missing:
                raise ForbiddenError(f"缺少权限：{', '.join(missing)}")
        elif not any(code in scope.permissions for code in codes):
            raise ForbiddenError("无权执行该操作")
        return scope

    return dependency


@dataclass
class RequestMeta:
    ip: str
    ua: str
    trace_id: str


def get_request_meta(request: Request) -> RequestMeta:
    from app.core.context import get_trace_id

    return RequestMeta(ip=get_client_ip(request), ua=get_user_agent(request), trace_id=get_trace_id())
