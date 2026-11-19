"""ORM → JSON 安全字典。

金额统一转为 float（前端展示），日期/时间转为 ISO 字符串；
业务对象可附带计算字段，避免前端二次拼装。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.security import decrypt_text, mask_bank_account, mask_email, mask_phone


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def to_dict(obj: Any, *, exclude: set[str] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if obj is None:
        return {}
    exclude = exclude or set()
    data: dict[str, Any] = {}
    table = getattr(obj, "__table__", None)
    if table is not None:
        for column in table.columns:
            name = column.name
            if name in exclude:
                continue
            data[name] = _json_value(getattr(obj, name))
    if extra:
        data.update({key: _json_value(value) for key, value in extra.items()})
    return data


def user_brief(user) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "position": user.position,
        "dept_id": user.dept_id,
    } if user is not None else {}


def expense(obj, item_rows=None) -> dict[str, Any]:
    data = to_dict(obj)
    if item_rows is not None:
        data["items"] = [to_dict(row) for row in item_rows]
    else:
        data["items"] = obj.items_json or []
    return data


def vendor(obj, *, sensitive: bool = False) -> dict[str, Any]:
    data = to_dict(obj)
    data.pop("blacklist_reason", None)
    if sensitive:
        data["blacklist_reason"] = obj.blacklist_reason
    return data


def contact(obj, *, sensitive: bool = False) -> dict[str, Any]:
    data = to_dict(obj, exclude={"phone_enc"})
    if obj.phone_enc:
        try:
            phone = decrypt_text(obj.phone_enc)
        except ValueError:
            phone = ""
        data["phone"] = phone if sensitive else mask_phone(phone)
    else:
        data["phone"] = ""
    return data


def bank(obj, *, sensitive: bool = False) -> dict[str, Any]:
    data = to_dict(obj, exclude={"account_no_enc"})
    try:
        account_no = decrypt_text(obj.account_no_enc)
    except ValueError:
        account_no = ""
    data["account_no"] = account_no if sensitive else mask_bank_account(account_no)
    return data


def customer(obj, *, sensitive: bool = False) -> dict[str, Any]:
    data = to_dict(obj, exclude={"phone_enc"})
    try:
        phone = decrypt_text(obj.phone_enc)
    except ValueError:
        phone = ""
    data["phone"] = phone if sensitive else mask_phone(phone)
    data["email"] = obj.email if sensitive else mask_email(obj.email)
    return data


def user_detail(obj, dept_name: str = "") -> dict[str, Any]:
    return to_dict(
        obj,
        exclude={"password_hash", "phone_enc"},
        extra={"dept_name": dept_name},
    )


def file_brief(obj) -> dict[str, Any]:
    return {
        "id": obj.id,
        "name": obj.name,
        "size": obj.size,
        "mime": obj.mime,
        "biz_type": obj.biz_type,
        "biz_id": obj.biz_id,
        "uploader_id": obj.uploader_id,
        "created_at": _json_value(obj.created_at),
    } if obj is not None else {}


def notification(obj) -> dict[str, Any]:
    data = to_dict(obj)
    return data


def workflow_task(task, instance=None, user_name: str = "") -> dict[str, Any]:
    data = to_dict(task)
    data["assignee_name"] = user_name
    if instance is not None:
        data["instance"] = {
            "id": instance.id,
            "title": instance.title,
            "biz_type": instance.biz_type,
            "biz_id": instance.biz_id,
            "status": instance.status,
            "current_node": instance.current_node,
            "initiator_id": instance.initiator_id,
            "start_at": _json_value(instance.start_at),
            "finish_at": _json_value(instance.finish_at),
        }
    return data
