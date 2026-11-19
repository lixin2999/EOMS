from __future__ import annotations

import base64
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.errors import ErrorCode, UnauthorizedError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
_AES_PREFIX = "enc:v1:"


# ------------------------------------------------------------------ 密码
def hash_password(password: str, *, username: str = "") -> str:
    return _hasher.hash(_pepper(password, username))


def verify_password(password: str, password_hash: str, *, username: str = "") -> bool:
    try:
        return _hasher.verify(password_hash, _pepper(password, username))
    except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


def _pepper(password: str, username: str) -> str:
    # 用户名参与 pepper，避免相同密码产生相同哈希；同时不影响后续用户名变更（变更时同步换哈希）
    return f"{password}::{settings.password_pepper}::{username.lower()}"


_PASSWORD_RULES = [
    (re.compile(r"[a-z]"), "小写字母"),
    (re.compile(r"[A-Z]"), "大写字母"),
    (re.compile(r"\d"), "数字"),
    (re.compile(r"[^A-Za-z0-9]"), "特殊字符"),
]


def check_password_strength(password: str, *, username: str = "") -> list[str]:
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"密码长度不得少于 {settings.password_min_length} 位")
    if len(password) > 64:
        errors.append("密码长度不得超过 64 位")
    categories = sum(1 for pattern, _ in _PASSWORD_RULES if pattern.search(password))
    if categories < 3:
        errors.append("密码需包含大写字母、小写字母、数字、特殊字符中的至少三类")
    if username and username.lower() in password.lower():
        errors.append("密码不得包含用户名")
    if password.lower() in {"12345678", "password", "admin123", "qwerty123"}:
        errors.append("密码过于简单")
    return errors


# ------------------------------------------------------------------ JWT
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_token(
    user_id: int,
    username: str,
    company_id: int,
    is_super: bool,
    token_type: str,
    password_ts: int = 0,
) -> tuple[str, str, datetime]:
    now = _now()
    ttl = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    expire = now + ttl
    jti = secrets.token_urlsafe(24)
    payload = {
        "sub": str(user_id),
        "username": username,
        "company_id": company_id,
        "is_super": is_super,
        "typ": token_type,
        "jti": jti,
        "pwd": password_ts,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return _encode(payload), jti, expire


def create_token_pair(
    user_id: int,
    username: str,
    company_id: int,
    is_super: bool,
    password_ts: int = 0,
) -> dict[str, Any]:
    access, access_jti, access_exp = create_token(user_id, username, company_id, is_super, "access", password_ts)
    refresh, refresh_jti, refresh_exp = create_token(user_id, username, company_id, is_super, "refresh", password_ts)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": int((access_exp - _now()).total_seconds()),
        "access_jti": access_jti,
        "access_exp": access_exp,
        "refresh_jti": refresh_jti,
        "refresh_exp": refresh_exp,
    }


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "jti", "typ"]},
            leeway=5,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已过期，请重新登录", ErrorCode.TOKEN_EXPIRED) from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("身份凭证无效") from exc
    if payload.get("typ") != expected_type:
        raise UnauthorizedError("身份凭证类型错误")
    return payload


# ------------------------------------------------------------------ 敏感字段加密（AES-256-GCM）
def encrypt_text(plain: str | None) -> str:
    if not plain:
        return ""
    nonce = os.urandom(12)
    cipher = AESGCM(settings.security_key)
    ciphertext = cipher.encrypt(nonce, plain.encode("utf-8"), None)
    return _AES_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_AES_PREFIX):
        # 兼容历史明文数据（迁移期）
        return value
    raw = base64.urlsafe_b64decode(value[len(_AES_PREFIX) :].encode("ascii"))
    cipher = AESGCM(settings.security_key)
    try:
        return cipher.decrypt(raw[:12], raw[12:], None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("敏感数据解密失败，请检查 EOMS_AES_KEY 是否变更") from exc


# ------------------------------------------------------------------ 脱敏
def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    if len(phone) <= 7:
        return phone[:2] + "*" * max(len(phone) - 2, 0)
    return f"{phone[:3]}****{phone[-4:]}"


def mask_bank_account(account: str | None) -> str:
    if not account:
        return ""
    digits = re.sub(r"\s+", "", account)
    if len(digits) <= 8:
        return "*" * len(digits)
    return f"{digits[:4]}****{digits[-4:]}"


def mask_id_card(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return email or ""
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def safe_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
