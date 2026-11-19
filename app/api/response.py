from __future__ import annotations

from typing import Any


def ok(data: Any = None, msg: str = "ok") -> dict[str, Any]:
    return {"code": 0, "msg": msg, "data": data}


def paged(result: dict, serializer) -> dict[str, Any]:
    return {
        "items": [serializer(item) for item in result.get("items", [])],
        "total": result.get("total", 0),
        "page": result.get("page", 1),
        "page_size": result.get("page_size", 20),
    }
