from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_trace_id
from app.core.logging import get_logger

logger = get_logger("eoms.error")


class ErrorCode:
    OK = 0
    BAD_REQUEST = 1000
    UNAUTHORIZED = 1001
    TOKEN_EXPIRED = 1002
    FORBIDDEN = 1003
    NOT_FOUND = 1004
    CONFLICT = 1005
    VALIDATION_ERROR = 1006
    RATE_LIMITED = 1007
    IDEMPOTENCY_CONFLICT = 1008
    ACCOUNT_LOCKED = 1009
    CAPTCHA_INVALID = 1010
    WORKFLOW_ERROR = 2000
    BUSINESS_RULE = 3000
    EXTERNAL_ERROR = 4000
    INTERNAL_ERROR = 5000


class AppError(Exception):
    """可预期业务异常，统一转换为 {code,msg,data,trace_id}。"""

    def __init__(
        self,
        msg: str,
        code: int = ErrorCode.BAD_REQUEST,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
    ) -> None:
        super().__init__(msg)
        self.msg = msg
        self.code = code
        self.http_status = http_status
        self.data = data

    def __repr__(self) -> str:
        return f"AppError(code={self.code}, msg={self.msg!r})"


class NotFoundError(AppError):
    def __init__(self, msg: str = "资源不存在") -> None:
        super().__init__(msg, ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)


class ForbiddenError(AppError):
    def __init__(self, msg: str = "无权访问该资源") -> None:
        super().__init__(msg, ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)


class UnauthorizedError(AppError):
    def __init__(self, msg: str = "登录状态已失效，请重新登录", code: int = ErrorCode.UNAUTHORIZED) -> None:
        super().__init__(msg, code, status.HTTP_401_UNAUTHORIZED)


class ConflictError(AppError):
    def __init__(self, msg: str = "数据已被修改，请刷新后重试") -> None:
        super().__init__(msg, ErrorCode.CONFLICT, status.HTTP_409_CONFLICT)


class BusinessRuleError(AppError):
    def __init__(self, msg: str) -> None:
        super().__init__(msg, ErrorCode.BUSINESS_RULE, status.HTTP_422_UNPROCESSABLE_ENTITY)


def error_body(code: int, msg: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "msg": msg, "data": data, "trace_id": get_trace_id()}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.http_status >= 500:
            logger.error("业务异常", extra={"action": "app_error"}, exc_info=exc)
        return JSONResponse(status_code=exc.http_status, content=error_body(exc.code, exc.msg, exc.data))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", []) if part not in {"body", "query", "path"})
            errors.append({"field": loc, "msg": item.get("msg", "参数不合法")})
        msg = errors[0]["msg"] if errors else "参数校验失败"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(ErrorCode.VALIDATION_ERROR, f"参数校验失败：{msg}", errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapping = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.BAD_REQUEST,
            429: ErrorCode.RATE_LIMITED,
        }
        code = mapping.get(exc.status_code, ErrorCode.BAD_REQUEST)
        detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
        if exc.status_code == 404:
            detail = "接口或资源不存在"
        return JSONResponse(status_code=exc.status_code, content=error_body(code, detail))

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("数据完整性冲突: %s", exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=error_body(ErrorCode.CONFLICT, "数据冲突：唯一键重复或关联数据不存在"),
        )

    @app.exception_handler(OperationalError)
    async def _operational_error(_: Request, exc: OperationalError) -> JSONResponse:
        logger.error("数据库操作异常: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_body(ErrorCode.EXTERNAL_ERROR, "数据库繁忙或连接超时，请稍后重试"),
        )

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        logger.error("数据库异常: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(ErrorCode.INTERNAL_ERROR, "数据库处理失败"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.error("未处理异常", exc_info=exc)
        detail = "服务器内部错误" if not getattr(app.state, "debug", False) else f"{type(exc).__name__}: {exc}"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(ErrorCode.INTERNAL_ERROR, detail),
        )
