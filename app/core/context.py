from __future__ import annotations

import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("eoms_trace_id", default="")
user_id_var: ContextVar[int | None] = ContextVar("eoms_user_id", default=None)
username_var: ContextVar[str] = ContextVar("eoms_username", default="")
client_ip_var: ContextVar[str] = ContextVar("eoms_client_ip", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str:
    return trace_id_var.get() or new_trace_id()


def set_trace_id(value: str | None = None) -> str:
    trace_id = value or new_trace_id()
    trace_id_var.set(trace_id)
    return trace_id
