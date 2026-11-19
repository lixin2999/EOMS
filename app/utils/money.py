from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import BusinessRuleError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: object, *, field_name: str = "金额") -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BusinessRuleError(f"{field_name}格式不正确") from exc
    if not result.is_finite():
        raise BusinessRuleError(f"{field_name}格式不正确")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def round_money(value: Decimal | float | int | str) -> Decimal:
    return to_decimal(value)


def safe_ratio(numerator: Decimal | float, denominator: Decimal | float, digits: int = 4) -> float:
    try:
        denominator_d = Decimal(str(denominator))
        if denominator_d == 0:
            return 0.0
        return float((Decimal(str(numerator)) / denominator_d).quantize(Decimal("1." + "0" * digits)))
    except (InvalidOperation, ValueError):
        return 0.0


def money_str(value: Decimal | float | int | None) -> str:
    return f"{to_decimal(value):.2f}"
