"""健康探针、金额四舍五入、敏感字段脱敏。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import BusinessRuleError
from app.core.security import (
    decrypt_text,
    encrypt_text,
    mask_bank_account,
    mask_email,
    mask_id_card,
    mask_phone,
)
from app.utils.money import money_str, safe_ratio, to_decimal


def test_health_and_ready(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ok"
    assert ready.json()["checks"]["database"]["ok"] is True


def test_root_metadata(client):
    body = client.get("/").json()
    assert body["data"]["version"] == "1.0.0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.005", "1.01"),
        ("1.004", "1.00"),
        ("-1.005", "-1.01"),
        (12.345, "12.35"),
        (None, "0.00"),
        ("", "0.00"),
    ],
)
def test_money_round_half_up(raw, expected):
    assert to_decimal(raw) == Decimal(expected)
    assert money_str(raw) == expected


def test_money_rejects_invalid_values():
    with pytest.raises(BusinessRuleError):
        to_decimal("abc")
    with pytest.raises(BusinessRuleError):
        to_decimal("NaN")


def test_safe_ratio():
    assert safe_ratio(1, 3, digits=2) == 0.33
    assert safe_ratio(1, 0) == 0.0


def test_encrypt_decrypt_roundtrip():
    cipher = encrypt_text("13800001234")
    assert cipher and cipher != "13800001234"
    assert decrypt_text(cipher) == "13800001234"
    assert decrypt_text(None) in (None, "")


def test_masking_helpers():
    assert mask_phone("13800001234") == "138****1234"
    assert mask_phone(None) == ""
    assert mask_email("alice@example.com") == "al***@example.com"
    assert mask_bank_account("6222020200112233445") == "6222****3445"
    assert mask_id_card("310101199001011234") == "3101**********1234"


def test_customer_phone_is_masked_in_api(client, auth):
    response = client.get("/api/v1/iam/customers", headers=auth("director"))
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    assert items
    for item in items:
        assert "phone_enc" not in item
        phone = item.get("phone") or ""
        if phone:
            assert "*" in phone, "客户手机号必须脱敏展示"
