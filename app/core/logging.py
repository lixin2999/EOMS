from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.context import client_ip_var, get_trace_id, user_id_var, username_var


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志，含 trace_id / user / ip，便于 Loki 检索。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": get_trace_id(),
            "user_id": user_id_var.get(),
            "username": username_var.get(),
            "ip": client_ip_var.get(),
        }
        for key in ("method", "path", "status", "duration_ms", "action", "target_type", "target_id", "extra"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    level = logging.DEBUG if settings.debug else logging.INFO
    root = logging.getLogger()
    if getattr(root, "_eoms_configured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root._eoms_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
