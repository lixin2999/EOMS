from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """全局配置。所有密钥均通过环境变量注入，不落库、不进镜像。"""

    model_config = SettingsConfigDict(
        env_prefix="EOMS_",
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "企业运营管理系统"
    env: str = "dev"
    debug: bool = False
    secret_key: str = "eoms-dev-secret-key-change-in-production"
    timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api/v1"
    trusted_hosts: str = "*"

    database_url: str = ""
    db_echo: bool = False
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 10
    db_statement_timeout_ms: int = 15000
    rls_enabled: bool = True

    redis_url: str = ""
    redis_timeout: float = 2.0

    access_token_minutes: int = 30
    refresh_token_days: int = 3
    login_max_fail: int = 5
    login_lock_minutes: int = 15
    max_sessions: int = 3
    captcha_ttl: int = 120
    password_min_length: int = 8
    password_expire_days: int = 90

    # Cookie 认证（P2-15）：令牌不下发给前端 JS，改用 HttpOnly Cookie + CSRF Token。
    cookie_secure: bool | None = None  # 未配置时：生产默认 True，其他环境 False
    cookie_samesite: str = "lax"
    cookie_domain: str = ""
    access_cookie_name: str = "eoms_at"
    refresh_cookie_name: str = "eoms_rt"
    csrf_cookie_name: str = "eoms_csrf"

    aes_key: str = ""

    storage_backend: str = "local"  # minio | local
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "eoms"
    minio_secret_key: str = "eoms-minio-secret"
    minio_bucket: str = "eoms"
    minio_secure: bool = False
    local_storage_dir: str = ".data/storage"
    max_upload_mb: int = 30
    presign_expire_seconds: int = 900

    workflow_due_hours: int = 24
    workflow_lock_seconds: int = 60
    budget_alert_threshold: float = 0.9

    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_ssl: bool = True

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_always_eager: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    rate_limit_per_minute: int = 300
    login_rate_limit_per_minute: int = 10
    files_rate_limit_per_minute: int = 60
    idempotency_ttl: int = 86400

    @field_validator("env")
    @classmethod
    def _validate_env(cls, value: str) -> str:
        value = value.lower()
        if value not in {"dev", "staging", "prod", "test"}:
            raise ValueError("EOMS_ENV 必须是 dev/staging/prod/test 之一")
        return value

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        """生产环境禁止以默认/占位密钥启动，避免 JWT 可伪造与敏感字段不可解。"""
        if self.env != "prod":
            return self
        secret = (self.secret_key or "").strip()
        if len(secret) < 32 or secret.startswith("eoms-dev") or "CHANGE_ME" in secret.upper():
            raise ValueError("生产环境必须通过 EOMS_SECRET_KEY 配置至少 32 位的随机密钥")
        if not self.aes_key:
            raise ValueError("生产环境必须配置 EOMS_AES_KEY（32 字节 base64 或 hex）")
        try:
            _ = self.security_key
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if self.storage_backend == "minio":
            minio_secret = (self.minio_secret_key or "").strip()
            if len(minio_secret) < 12 or minio_secret == "eoms-minio-secret" or "CHANGE_ME" in minio_secret.upper():
                raise ValueError("生产环境必须通过 EOMS_MINIO_SECRET_KEY 配置强密码")
        return self

    # ---------------- 派生属性 ----------------
    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def cookie_secure_flag(self) -> bool:
        """Cookie 是否带 Secure：未显式配置时生产默认为真。"""
        return self.is_prod if self.cookie_secure is None else self.cookie_secure

    @property
    def sqlite_path(self) -> Path:
        path = Path(self.local_storage_dir).parent / "eoms.db"
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.sqlite_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.resolved_database_url.startswith("postgresql")

    @property
    def local_storage_path(self) -> Path:
        path = Path(self.local_storage_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def security_key(self) -> bytes:
        """密钥材料统一派生为 32 字节，用于 AES-GCM。"""
        if self.aes_key:
            raw = self.aes_key.strip()
            try:
                decoded = base64.b64decode(raw, validate=True)
                if len(decoded) == 32:
                    return decoded
            except Exception:  # noqa: BLE001 - 允许 hex 形式
                pass
            try:
                decoded = bytes.fromhex(raw)
                if len(decoded) == 32:
                    return decoded
            except ValueError:
                pass
            raise ValueError("EOMS_AES_KEY 必须是 32 字节的 base64 或 hex 字符串")
        return hashlib.sha256(self.secret_key.encode("utf-8")).digest()

    @property
    def celery_eager(self) -> bool:
        return self.celery_always_eager or self.env in {"dev", "test"} and not self.redis_enabled

    @property
    def password_pepper(self) -> str:
        return hashlib.sha256(f"eoms-pwd:{self.secret_key}".encode()).hexdigest()[:16]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def _sqlite_url_for_tests(path: str) -> str:
    """测试辅助：生成绝对路径 SQLite URL（Windows 盘符需特殊编码）。"""
    if os.name == "nt":
        return "sqlite:///" + quote_plus(path.replace("\\", "/"), safe="/:")
    return f"sqlite:///{path}"


def settings_summary() -> dict[str, object]:
    """用于日志/健康检查的非敏感配置摘要。"""
    return {
        "env": settings.env,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "redis": settings.redis_enabled,
        "storage": settings.storage_backend,
        "rls": settings.rls_enabled and settings.is_postgres,
        "timezone": settings.timezone,
    }


def dumps_for_log(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def random_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
