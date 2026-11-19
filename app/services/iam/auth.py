from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import LockBusyError, cache
from app.core.config import settings
from app.core.errors import AppError, BusinessRuleError, ErrorCode, UnauthorizedError
from app.core.logging import get_logger
from app.core.scope import ScopeContext, build_scope, visible_menu_tree
from app.core.security import (
    check_password_strength,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserStatus
from app.models.iam import Company, Dept, LoginLog, Role, User
from app.services.iam.audit import write_audit
from app.utils.captcha import generate_captcha
from app.utils.datetime import now

logger = get_logger("eoms.auth")
_DUMMY_HASH = hash_password("eoms-dummy-password", username="dummy")


# ---------------------------------------------------------------- 验证码
def create_captcha() -> dict[str, Any]:
    code, image = generate_captcha()
    captcha_id = f"{now().timestamp():.6f}-{id(code)}"
    import uuid

    captcha_id = uuid.uuid4().hex
    cache.set(f"captcha:{captcha_id}", code.lower(), settings.captcha_ttl)
    return {"captcha_id": captcha_id, "image": image, "expires_in": settings.captcha_ttl}


def _verify_captcha(captcha_id: str, code: str) -> None:
    key = f"captcha:{captcha_id}"
    expected = cache.get(key)
    cache.delete(key)  # 一次性使用，防止重放
    if not expected or not code or expected != code.strip().lower():
        raise AppError("验证码错误或已过期", ErrorCode.CAPTCHA_INVALID, 400)


# ---------------------------------------------------------------- 登录失败锁定 / 会话
def _fail_key(username: str) -> str:
    return f"login:fail:{username.lower()}"


def _check_locked(username: str) -> None:
    raw = cache.get(_fail_key(username))
    if raw and int(raw) >= settings.login_max_fail:
        raise AppError(
            f"登录失败次数过多，账号已临时锁定，请 {settings.login_lock_minutes} 分钟后重试",
            ErrorCode.ACCOUNT_LOCKED,
            423,
        )


def _record_failure(username: str) -> None:
    key = _fail_key(username)
    count = cache.incr(key, settings.login_lock_minutes * 60)
    if count >= settings.login_max_fail:
        cache.set(key, str(count), settings.login_lock_minutes * 60)


def _clear_failure(username: str) -> None:
    cache.delete(_fail_key(username))


def _session_key(user_id: int) -> str:
    return f"sess:{user_id}"


def _load_sessions(user_id: int) -> list[dict[str, Any]]:
    raw = cache.get_json(_session_key(user_id)) or []
    current = datetime.now(timezone.utc)
    result = []
    for item in raw:
        try:
            expire_at = datetime.fromisoformat(item["expire_at"])
        except (KeyError, ValueError):
            continue
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
        if expire_at > current:
            result.append(item)
    return result


def _register_session(user_id: int, jti: str, expire_at: datetime, ip: str, ua: str) -> None:
    try:
        with cache.lock(f"sess:{user_id}", ttl=10):
            sessions = _load_sessions(user_id)
            sessions = [item for item in sessions if item.get("jti") != jti]
            sessions.append(
                {
                    "jti": jti,
                    "expire_at": expire_at.isoformat(),
                    "ip": ip,
                    "ua": ua[:255],
                    "login_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if len(sessions) > settings.max_sessions:
                sessions = sessions[-settings.max_sessions :]
            cache.set_json(_session_key(user_id), sessions, settings.refresh_token_days * 86400)
    except LockBusyError:
        logger.warning("会话登记锁冲突 user_id=%s", user_id)


def _remove_session(user_id: int, jti: str) -> None:
    sessions = [item for item in _load_sessions(user_id) if item.get("jti") != jti]
    cache.set_json(_session_key(user_id), sessions, settings.refresh_token_days * 86400)


def _clear_sessions(user_id: int) -> None:
    cache.delete(_session_key(user_id))


def _blacklist(jti: str, token_type: str, expire_ts: int) -> None:
    ttl = max(int(expire_ts - datetime.now().timestamp()), 1)
    cache.set(f"bl:{token_type}:{jti}", "1", ttl)


# ---------------------------------------------------------------- 登录
def login(
    db: Session,
    *,
    username: str,
    password: str,
    captcha_id: str,
    captcha_code: str,
    ip: str,
    ua: str,
) -> dict[str, Any]:
    username = (username or "").strip()
    if not username or not password:
        raise AppError("请输入用户名和密码", ErrorCode.BAD_REQUEST, 400)
    if not cache.allow(f"login:ip:{ip}", settings.login_rate_limit_per_minute):
        raise AppError("登录请求过于频繁，请稍后再试", ErrorCode.RATE_LIMITED, 429)
    _check_locked(username)
    _verify_captcha(captcha_id, captcha_code)

    user = db.execute(select(User).where(func.lower(User.username) == username.lower())).scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_HASH, username="dummy")
        _record_failure(username)
        _write_login_log(db, None, username, ip, ua, False, "用户不存在")
        raise UnauthorizedError("用户名或密码错误")

    if user.status != UserStatus.ACTIVE.value:
        _write_login_log(db, user, user.username, ip, ua, False, "账号已停用")
        raise AppError("账号已停用，请联系管理员", ErrorCode.ACCOUNT_LOCKED, 403)

    company = db.get(Company, user.company_id)
    if company is None or company.status != "ACTIVE":
        _write_login_log(db, user, user.username, ip, ua, False, "公司已停用")
        raise AppError("所属公司已停用，请联系管理员", ErrorCode.ACCOUNT_LOCKED, 403)

    if not verify_password(password, user.password_hash, username=user.username):
        _record_failure(username)
        _write_login_log(db, user, user.username, ip, ua, False, "密码错误")
        remaining = settings.login_max_fail - int(cache.get(_fail_key(username)) or 0)
        hint = f"，还可尝试 {remaining} 次" if remaining > 0 else ""
        raise UnauthorizedError(f"用户名或密码错误{hint}")

    _clear_failure(username)
    user.last_login_at = now()
    db.flush()
    _write_login_log(db, user, user.username, ip, ua, True, None)

    password_ts = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0
    pair = create_token_pair(user.id, user.username, user.company_id, user.is_super, password_ts)
    _register_session(user.id, pair["refresh_jti"], pair["refresh_exp"], ip, ua)
    scope = build_scope(db, user)

    return {
        "access_token": pair["access_token"],
        "refresh_token": pair["refresh_token"],
        "token_type": "Bearer",
        "expires_in": pair["expires_in"],
        "user": user_profile(db, user, scope),
    }


def _write_login_log(
    db: Session, user: User | None, username: str, ip: str, ua: str, success: bool, reason: str | None
) -> None:
    db.add(
        LoginLog(
            company_id=user.company_id if user else None,
            user_id=user.id if user else None,
            username=username,
            ip=ip,
            ua=ua[:255],
            success=success,
            reason=reason,
        )
    )
    db.flush()


# ---------------------------------------------------------------- 刷新 / 登出
def refresh(db: Session, refresh_token: str, ip: str, ua: str) -> dict[str, Any]:
    payload = decode_token(refresh_token, "refresh")
    jti = str(payload.get("jti") or "")
    if cache.get(f"bl:refresh:{jti}"):
        raise UnauthorizedError("登录已失效，请重新登录")
    user_id = int(payload.get("sub", "0"))
    sessions = _load_sessions(user_id)
    if not any(item.get("jti") == jti for item in sessions):
        raise UnauthorizedError("登录已失效，请重新登录")
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("账号不存在或已停用")
    password_ts = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0
    if int(payload.get("pwd", 0)) != password_ts:
        raise UnauthorizedError("密码已变更，请重新登录")

    expire_ts = int(payload.get("exp", 0))
    # 原子轮换：同一 refresh 只能成功换一次。抢占失败说明已使用过，
    # 按令牌重放处理：作废该令牌与用户全部会话，强制重新登录。
    replay_ttl = max(expire_ts - int(datetime.now().timestamp()), 1)
    if not cache.set_nx(f"rot:{jti}", str(user.id), replay_ttl):
        _blacklist(jti, "refresh", expire_ts)
        _clear_sessions(user.id)
        write_audit(
            db,
            user=None,
            action="REFRESH_REPLAY_DETECTED",
            target_type="USER",
            target_id=user.id,
            company_id=user.company_id,
            after={"jti": jti, "ip": ip, "ua": ua[:255]},
        )
        logger.warning("刷新令牌重放检测 user_id=%s jti=%s ip=%s", user.id, jti, ip)
        raise UnauthorizedError("登录已失效，请重新登录")
    _blacklist(jti, "refresh", expire_ts)
    _remove_session(user.id, jti)

    pair = create_token_pair(user.id, user.username, user.company_id, user.is_super, password_ts)
    _register_session(user.id, pair["refresh_jti"], pair["refresh_exp"], ip, ua)
    return {
        "access_token": pair["access_token"],
        "refresh_token": pair["refresh_token"],
        "token_type": "Bearer",
        "expires_in": pair["expires_in"],
    }


def logout(user: User, access_jti: str, access_exp: int, refresh_token: str | None) -> None:
    if access_jti:
        _blacklist(access_jti, "access", access_exp)
    if refresh_token:
        try:
            payload = decode_token(refresh_token, "refresh")
            _blacklist(str(payload.get("jti")), "refresh", int(payload.get("exp", 0)))
            _remove_session(user.id, str(payload.get("jti")))
        except AppError:
            pass


# ---------------------------------------------------------------- 用户资料
def user_profile(db: Session, user: User, scope: ScopeContext | None = None) -> dict[str, Any]:
    scope = scope or build_scope(db, user)
    dept = db.get(Dept, user.dept_id) if user.dept_id else None
    company = db.get(Company, user.company_id)
    roles = []
    if user.role_ids:
        roles = list(db.execute(select(Role).where(Role.id.in_(user.role_ids))).scalars().all())
    password_expired = bool(
        settings.password_expire_days > 0
        and user.password_updated_at
        and user.password_updated_at + timedelta(days=settings.password_expire_days) < now()
    )
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "position": user.position,
        "avatar": user.avatar,
        "email": user.email,
        "company_id": user.company_id,
        "company_name": company.name if company else "",
        "dept_id": user.dept_id,
        "dept_name": dept.name if dept else "",
        "role_ids": user.role_ids or [],
        "roles": [
            {"id": role.id, "code": role.code, "name": role.name, "data_scope": role.data_scope}
            for role in roles
        ],
        "is_super": user.is_super,
        "first_login": user.first_login,
        "password_expired": password_expired,
        "permissions": sorted(scope.permissions) if not scope.is_super else ["*"],
        "menus": visible_menu_tree(db, scope),
        "last_login_at": user.last_login_at,
    }


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.password_hash, username=user.username):
        raise BusinessRuleError("原密码不正确")
    errors = check_password_strength(new_password, username=user.username)
    if errors:
        raise BusinessRuleError("；".join(errors))
    if old_password == new_password:
        raise BusinessRuleError("新密码不能与原密码相同")
    user.password_hash = hash_password(new_password, username=user.username)
    user.password_updated_at = now()
    user.first_login = False
    user.version = (user.version or 1) + 1
    _clear_sessions(user.id)
    write_audit(db, user=user, action="CHANGE_PASSWORD", target_type="USER", target_id=user.id)
    db.flush()


def reset_password(db: Session, operator: User, target: User, new_password: str, force_change: bool = True) -> None:
    errors = check_password_strength(new_password, username=target.username)
    if errors:
        raise BusinessRuleError("；".join(errors))
    target.password_hash = hash_password(new_password, username=target.username)
    target.password_updated_at = now()
    target.first_login = force_change
    target.version = (target.version or 1) + 1
    _clear_sessions(target.id)
    write_audit(
        db,
        user=operator,
        action="RESET_PASSWORD",
        target_type="USER",
        target_id=target.id,
        after={"username": target.username},
    )
    db.flush()
