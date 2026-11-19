from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.context import client_ip_var, get_trace_id, user_id_var, username_var
from app.models.iam import AuditLog, User

SENSITIVE_FIELDS = {
    "password_hash",
    "phone_enc",
    "account_no_enc",
    "id_card_enc",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def snapshot(obj: Any, fields: list[str] | None = None) -> dict[str, Any]:
    if obj is None:
        return {}
    mapper = sa_inspect(obj).mapper
    names = fields or [column.key for column in mapper.column_attrs]
    return {
        name: _jsonable(getattr(obj, name))
        for name in names
        if name not in SENSITIVE_FIELDS and not name.endswith("_enc")
    }


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            result[key] = {"before": before.get(key), "after": after.get(key)}
    return result


def write_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    company_id: int | None = None,
) -> AuditLog:
    log = AuditLog(
        company_id=company_id or (user.company_id if user else None),
        user_id=user.id if user else user_id_var.get(),
        username=user.username if user else (username_var.get() or None),
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        before_json=_jsonable(before) if before else None,
        after_json=_jsonable(after) if after else None,
        ip=client_ip_var.get() or None,
        ua=None,
        trace_id=get_trace_id(),
    )
    db.add(log)
    db.flush()
    return log
