"""EOMS 应用入口：中间件（trace_id / 限流 / 幂等 / 安全头）、路由与健康检查。"""

from __future__ import annotations

import hmac
import json
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.cache import cache
from app.core.config import settings, settings_summary
from app.core.context import (
    client_ip_var,
    get_trace_id,
    set_trace_id,
    user_id_var,
    username_var,
)
from app.core.errors import error_body, register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.security import decode_token
from app.db.session import SessionLocal, init_db
from app.services import storage

setup_logging()
logger = get_logger("eoms.main")

SKIP_RATE_LIMIT = {"/healthz", "/readyz", "/metrics", "/docs", "/redoc", "/openapi.json", "/"}
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# 建立会话前无凭证可用：登录/刷新/验证码不参与 CSRF 校验（避免旧 Cookie 阻断重新登录）
CSRF_EXEMPT = {
    f"{settings.api_prefix}/auth/login",
    f"{settings.api_prefix}/auth/refresh",
    f"{settings.api_prefix}/auth/captcha",
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else ""


def _access_token(request: Request) -> str:
    """取访问令牌：Authorization 头优先，其次 HttpOnly Cookie（浏览器会话）。"""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(settings.access_cookie_name) or ""


class ContextMiddleware(BaseHTTPMiddleware):
    """注入 trace_id / 客户端信息，并在响应头回传 trace_id。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = set_trace_id(request.headers.get("x-trace-id"))
        ip = _client_ip(request)
        ip_token = client_ip_var.set(ip)
        user_token = user_id_var.set(None)
        name_token = username_var.set("")
        request.state.trace_id = trace_id
        request.state.client_ip = ip
        token = _access_token(request)
        if token:
            try:
                payload = decode_token(token, "access")
                user_id_var.set(int(payload.get("sub", "0")))
                username_var.set(str(payload.get("username") or ""))
            except Exception:  # noqa: BLE001 - 认证失败交由依赖处理
                pass
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            client_ip_var.reset(ip_token)
            user_id_var.reset(user_token)
            username_var.reset(name_token)
            raise
        duration = (time.perf_counter() - started) * 1000
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration, 2),
            },
        )
        client_ip_var.reset(ip_token)
        user_id_var.reset(user_token)
        username_var.reset(name_token)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if settings.is_prod and request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """令牌桶限流：登录、文件下载、其它接口使用独立桶，避免大文件下载抢占配额。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in SKIP_RATE_LIMIT:
            return await call_next(request)
        ip = _client_ip(request) or "unknown"
        if path == f"{settings.api_prefix}/auth/login":
            bucket, limit = f"login:{ip}", settings.login_rate_limit_per_minute
        elif path.startswith(f"{settings.api_prefix}/files/"):
            bucket, limit = f"files:{ip}", settings.files_rate_limit_per_minute
        else:
            bucket, limit = f"api:{ip}", settings.rate_limit_per_minute
        allowed, remaining = cache.allow(bucket, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
                content=error_body(1007, "请求过于频繁，请稍后再试"),
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Cookie 会话的 CSRF 防护：写操作需带与 Cookie 一致的 ``X-CSRF-Token``。

    仅对「无 Authorization 头 + 存在访问 Cookie」的浏览器会话生效；
    使用 Bearer 的脚本/测试不受影响。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method not in CSRF_METHODS
            or not path.startswith(settings.api_prefix)
            or path in CSRF_EXEMPT
        ):
            return await call_next(request)
        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
        has_cookie = bool(request.cookies.get(settings.access_cookie_name))
        if not has_cookie or has_bearer:
            return await call_next(request)
        cookie_token = request.cookies.get(settings.csrf_cookie_name) or ""
        header_token = request.headers.get("x-csrf-token") or ""
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
            return JSONResponse(
                status_code=403,
                content=error_body(403, "CSRF 校验失败，请刷新页面重试"),
            )
        return await call_next(request)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等键：写操作携带 Idempotency-Key 时返回首次成功响应。"""

    async def dispatch(self, request: Request, call_next):
        if request.method not in IDEMPOTENT_METHODS:
            return await call_next(request)
        key = (request.headers.get("idempotency-key") or "").strip()
        if not key or len(key) > 128:
            return await call_next(request)
        token = _access_token(request)
        if not token:
            return await call_next(request)
        try:
            payload = decode_token(token, "access")
            company_id = int(payload.get("company_id", 0))
            user_id = int(payload.get("sub", 0))
        except Exception:  # noqa: BLE001
            return await call_next(request)
        cache_key = f"idem:{company_id}:{user_id}:{request.method}:{request.url.path}:{key}"
        cached = cache.get_json(cache_key)
        if isinstance(cached, dict) and "body" in cached:
            return JSONResponse(
                status_code=int(cached.get("status", 200)),
                content=cached["body"],
                headers={"Idempotency-Replayed": "true"},
            )
        # 同一幂等键并发请求互斥：抢占失败说明首次请求仍在处理，提示稍后重试。
        lock_key = f"idem-lock:{cache_key}"
        if not cache.set_nx(lock_key, "1", 30):
            return JSONResponse(
                status_code=409, content=error_body(1008, "相同请求正在处理中，请稍后重试")
            )
        try:
            return await self._forward(request, call_next, cache_key, company_id, user_id, key)
        finally:
            cache.delete(lock_key)

    async def _forward(
        self, request: Request, call_next, cache_key: str, company_id: int, user_id: int, key: str
    ) -> Response:
        response = await call_next(request)
        chunks = [chunk async for chunk in response.body_iterator]
        raw = b"".join(chunks)
        headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() not in {"content-length", "content-encoding"}
        }
        if response.status_code < 400 and raw:
            try:
                parsed: Any = json.loads(raw)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                return Response(
                    content=raw,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )
            cache.set_json(
                cache_key,
                {"status": response.status_code, "body": parsed},
                settings.idempotency_ttl,
            )
            _persist_idempotency(company_id, user_id, key, request, response.status_code, parsed)
        return Response(
            content=raw,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )


def _persist_idempotency(
    company_id: int, user_id: int, key: str, request: Request, status_code: int, body: Any
) -> None:
    """落库幂等记录。

    中间件在请求事务之外，无法共享主事务，因此独立 ``SessionLocal``；
    落库为旁路审计：主流程幂等以保证缓存为准，重复键仅回滚本会话。
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.platform import IdempotencyKey

    db = SessionLocal()
    try:
        db.add(
            IdempotencyKey(
                company_id=company_id,
                user_id=user_id,
                key=key,
                method=request.method,
                path=request.url.path[:255],
                status_code=status_code,
                response_json=body,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception as exc:  # noqa: BLE001 - 幂等落库失败不影响主流程
        db.rollback()
        logger.warning("幂等记录写入失败: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_sqlite and settings.env in {"dev", "test"}:
        init_db()
    try:
        from app.workflow.callbacks import ensure_handlers

        ensure_handlers()
    except Exception as exc:  # noqa: BLE001
        logger.warning("审批回调注册失败: %s", exc)
    logger.info("EOMS 启动完成 %s", settings_summary())
    yield
    logger.info("EOMS 已停止")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="审批 / 项目 / 供应商 / 成本 / 经营报表一体化平台",
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    lifespan=lifespan,
)

if settings.trusted_host_list and settings.trusted_host_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

# add_middleware 后注册者居外层：CORS 必须在最外层，使限流/幂等/CSRF 拒绝响应也带 CORS 头。
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)
# CSRF 依赖 ContextMiddleware 先绑定 trace_id，故必须注册在它之后（更内层）。
app.add_middleware(CsrfMiddleware)
app.add_middleware(ContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Trace-ID", "X-CSRF-Token"],
    expose_headers=["X-Trace-ID", "X-RateLimit-Remaining", "Idempotency-Replayed"],
    max_age=600,
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "code": 0,
        "msg": "ok",
        "data": {"app": settings.app_name, "version": "1.0.0", "docs": None if settings.is_prod else "/docs"},
    }


@app.get("/healthz", tags=["健康检查"], summary="存活探针")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz", tags=["健康检查"], summary="就绪探针")
def readyz() -> Response:
    checks: dict[str, Any] = {}
    ok_flag = True
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = {"ok": True}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        ok_flag = False
        checks["database"] = {"ok": False, "error": str(exc)}
    checks["cache"] = cache.health()
    if not checks["cache"].get("ok", False):
        ok_flag = False
    checks["storage"] = storage.health()
    if not checks["storage"].get("ok", False):
        ok_flag = False
    return JSONResponse(
        status_code=200 if ok_flag else 503,
        content={"status": "ok" if ok_flag else "degraded", "checks": checks, "trace_id": get_trace_id()},
    )


try:  # pragma: no cover - 依赖缺失时降级
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/healthz", "/readyz"],
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except Exception as exc:  # noqa: BLE001
    logger.warning("Prometheus 指标未启用: %s", exc)
