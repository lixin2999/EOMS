from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ok
from app.core.deps import CurrentUser, DbSession, get_client_ip, get_user_agent
from app.schemas.common import ChangePasswordIn, LoginIn, LogoutIn, RefreshIn
from app.services.iam import auth as auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/captcha", summary="获取图形验证码")
def captcha() -> dict:
    return ok(auth_service.create_captcha())


@router.post("/login", summary="账号密码登录")
def login(payload: LoginIn, request: Request, db: DbSession) -> dict:
    data = auth_service.login(
        db,
        username=payload.username,
        password=payload.password,
        captcha_id=payload.captcha_id,
        captcha_code=payload.captcha_code,
        ip=get_client_ip(request),
        ua=get_user_agent(request),
    )
    return ok(data, "登录成功")


@router.post("/refresh", summary="刷新令牌")
def refresh(payload: RefreshIn, request: Request, db: DbSession) -> dict:
    data = auth_service.refresh(db, payload.refresh_token, get_client_ip(request), get_user_agent(request))
    return ok(data)


@router.post("/logout", summary="登出")
def logout(payload: LogoutIn, request: Request, db: DbSession, user: CurrentUser) -> dict:
    token_payload = getattr(request.state, "token_payload", {})
    auth_service.logout(
        user,
        getattr(request.state, "jti", ""),
        int(token_payload.get("exp", 0)),
        payload.refresh_token,
    )
    return ok(None, "已安全退出")


@router.get("/me", summary="当前用户信息与权限")
def me(db: DbSession, user: CurrentUser) -> dict:
    return ok(auth_service.user_profile(db, user))


@router.put("/password", summary="修改密码")
def change_password(payload: ChangePasswordIn, db: DbSession, user: CurrentUser) -> dict:
    auth_service.change_password(db, user, payload.old_password, payload.new_password)
    return ok(None, "密码修改成功，请重新登录")
