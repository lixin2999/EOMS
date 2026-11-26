from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Request, Response

from app.api.response import ok
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, get_client_ip, get_user_agent
from app.core.errors import UnauthorizedError
from app.schemas.common import ChangePasswordIn, LoginIn, LogoutIn, RefreshIn
from app.services.iam import auth as auth_service

router = APIRouter(prefix="/auth", tags=["认证"])

REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"


def _cookie_domain() -> str | None:
    return settings.cookie_domain or None


def _set_session_cookies(response: Response, data: dict[str, Any]) -> str:
    """写入 access/refresh（HttpOnly）与 CSRF（可读）三类 Cookie，返回 CSRF token。"""
    max_age_refresh = settings.refresh_token_days * 86400
    base: dict[str, Any] = {
        "secure": settings.cookie_secure_flag,
        "samesite": settings.cookie_samesite,
        "domain": _cookie_domain(),
    }
    response.set_cookie(
        settings.access_cookie_name,
        data["access_token"],
        max_age=int(data["expires_in"]),
        path="/",
        httponly=True,
        **base,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        data["refresh_token"],
        max_age=max_age_refresh,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        **base,
    )
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age_refresh,
        path="/",
        httponly=False,
        **base,
    )
    return csrf_token


def _clear_session_cookies(response: Response) -> None:
    for name in (settings.access_cookie_name, settings.refresh_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", domain=_cookie_domain())
    response.delete_cookie(settings.refresh_cookie_name, path=REFRESH_COOKIE_PATH, domain=_cookie_domain())


@router.get("/captcha", summary="获取图形验证码")
def captcha() -> dict:
    return ok(auth_service.create_captcha())


@router.post("/login", summary="账号密码登录")
def login(payload: LoginIn, request: Request, response: Response, db: DbSession) -> dict:
    data = auth_service.login(
        db,
        username=payload.username,
        password=payload.password,
        captcha_id=payload.captcha_id,
        captcha_code=payload.captcha_code,
        ip=get_client_ip(request),
        ua=get_user_agent(request),
    )
    csrf_token = _set_session_cookies(response, data)
    # 令牌仅存在于 HttpOnly Cookie，响应体只回传用户资料与前端可读的 CSRF token。
    return ok(
        {"user": data["user"], "expires_in": data["expires_in"], "csrf_token": csrf_token},
        "登录成功",
    )


@router.post("/refresh", summary="刷新令牌")
def refresh(request: Request, response: Response, db: DbSession, payload: RefreshIn | None = None) -> dict:
    # 浏览器仅依赖 HttpOnly Cookie，允许不发送 JSON 请求体；旧客户端仍可显式传 refresh_token。
    token = (payload.refresh_token if payload else None) or request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise UnauthorizedError("登录已失效，请重新登录")
    data = auth_service.refresh(db, token, get_client_ip(request), get_user_agent(request))
    csrf_token = _set_session_cookies(response, data)
    return ok({"expires_in": data["expires_in"], "csrf_token": csrf_token})


@router.post("/logout", summary="登出")
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    user: CurrentUser,
    payload: LogoutIn | None = None,
) -> dict:
    token_payload = getattr(request.state, "token_payload", {})
    auth_service.logout(
        user,
        getattr(request.state, "jti", ""),
        int(token_payload.get("exp", 0)),
        (payload.refresh_token if payload else None) or request.cookies.get(settings.refresh_cookie_name),
    )
    _clear_session_cookies(response)
    return ok(None, "已安全退出")


@router.get("/me", summary="当前用户信息与权限")
def me(db: DbSession, user: CurrentUser) -> dict:
    return ok(auth_service.user_profile(db, user))


@router.put("/password", summary="修改密码")
def change_password(payload: ChangePasswordIn, response: Response, db: DbSession, user: CurrentUser) -> dict:
    auth_service.change_password(db, user, payload.old_password, payload.new_password)
    _clear_session_cookies(response)
    return ok(None, "密码修改成功，请重新登录")