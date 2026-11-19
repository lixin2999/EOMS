from __future__ import annotations

from decimal import Decimal

# 费用科目（与 scripts/seed.py 预置科目一致）
CATEGORY_ACCOUNT: dict[str, str] = {
    "TRAVEL": "5601",
    "ENTERTAIN": "5602",
    "OFFICE": "5603",
    "SUBCONTRACT": "5401",
    "MATERIAL": "5402",
    "OTHER": "5609",
}

ACCOUNT_NAMES: dict[str, str] = {
    "5401": "分包成本",
    "5402": "材料成本",
    "5601": "差旅费",
    "5602": "业务招待费",
    "5603": "办公费",
    "5609": "其他费用",
}


def account_for_category(category: str) -> str:
    return CATEGORY_ACCOUNT.get(category, "5609")


def category_amounts(items: list[dict]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for item in items:
        code = account_for_category(str(item.get("category") or "OTHER"))
        amount = Decimal(str(item.get("amount") or 0))
        result[code] = result.get(code, Decimal("0")) + amount
    return result
