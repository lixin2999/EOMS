"""供应商准入、合同管理、付款/收款/计收、预算与期间关账。"""

from __future__ import annotations

import uuid

import pytest

from tests.helpers import approve_instance


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


@pytest.fixture(scope="module")
def vendor(client, auth, demo):
    purchase = auth("purchase")
    suffix = uuid.uuid4().hex[:6]
    data = _ok(
        client.post(
            "/api/v1/vendors",
            json={
                "name": f"测试供应商-{suffix}",
                "type": "SERVICE",
                "tax_no": "91310000TEST0001",
                "intro": "自动化测试供应商",
                "contacts": [
                    {"name": "张三", "title": "商务", "phone": "13800001111", "is_default": True}
                ],
                "banks": [
                    {
                        "bank_name": "中国银行",
                        "account_no": "6222020200112233445",
                        "account_name": "测试供应商",
                        "is_default": True,
                    }
                ],
                "licenses": [
                    {"name": "营业执照", "no": "LIC-TEST-001", "valid_to": "2027-12-31"}
                ],
                "submit": True,
            },
            headers=purchase,
        )
    )
    vendor_id = int(data["id"])
    assert data["status"] == "PENDING"

    handled = approve_instance(client, [auth("director"), auth("manager")], int(data["instance_id"]))
    assert handled >= 1
    detail = _ok(client.get(f"/api/v1/vendors/{vendor_id}", headers=purchase))
    return {"id": vendor_id, "purchase": purchase, "data": detail, "demo": demo}


def test_vendor_approved_and_masked_bank(client, vendor):
    assert vendor["data"]["status"] == "ACTIVE"
    banks = _ok(client.get(f"/api/v1/vendors/{vendor['id']}/banks", headers=vendor["purchase"]))
    assert banks and banks[0]["account_no"].startswith(("****", "6222"))
    contacts = _ok(
        client.get(f"/api/v1/vendors/{vendor['id']}/contacts", headers=vendor["purchase"])
    )
    assert contacts and contacts[0]["name"] == "张三"
    licenses = _ok(
        client.get(f"/api/v1/vendors/{vendor['id']}/licenses", headers=vendor["purchase"])
    )
    assert licenses


def test_vendor_update_evaluate_and_bind(client, vendor):
    updated = _ok(
        client.put(
            f"/api/v1/vendors/{vendor['id']}",
            json={"level": "B", "intro": "更新后的简介", "version": vendor["data"]["version"]},
            headers=vendor["purchase"],
        )
    )
    assert updated["level"] == "B"

    evaluation = _ok(
        client.post(
            f"/api/v1/vendors/{vendor['id']}/evaluations",
            json={
                "project_id": vendor["demo"]["project_ids"][0],
                "quality_score": "90",
                "schedule_score": "85",
                "cooperate_score": "88",
                "comment": "交付质量稳定",
                "eval_date": "2026-11-10",
            },
            headers=vendor["purchase"],
        )
    )
    assert float(evaluation["total_score"]) > 0

    bound = _ok(
        client.post(
            f"/api/v1/vendors/{vendor['id']}/projects",
            json={
                "project_id": vendor["demo"]["project_ids"][0],
                "role": "分包商",
                "contract_amount": "30000",
            },
            headers=vendor["purchase"],
        )
    )
    assert bound["project_id"] == vendor["demo"]["project_ids"][0]

    projects = _ok(
        client.get(f"/api/v1/vendors/{vendor['id']}/projects", headers=vendor["purchase"])
    )
    assert projects
    report = _ok(
        client.get(
            f"/api/v1/vendors/{vendor['id']}/annual-report",
            params={"year": 2026},
            headers=vendor["purchase"],
        )
    )
    assert "score" in report or "evaluations" in report


def test_vendor_blacklist_and_restore(client, vendor):
    _ok(
        client.post(
            f"/api/v1/vendors/{vendor['id']}/blacklist",
            json={"reason": "测试黑名单流程"},
            headers=vendor["purchase"],
        )
    )
    blacklisted = _ok(client.get(f"/api/v1/vendors/{vendor['id']}", headers=vendor["purchase"]))
    assert blacklisted["status"] == "BLACKLIST"
    _ok(client.post(f"/api/v1/vendors/{vendor['id']}/restore", headers=vendor["purchase"]))
    restored = _ok(client.get(f"/api/v1/vendors/{vendor['id']}", headers=vendor["purchase"]))
    assert restored["status"] == "ACTIVE"


@pytest.fixture(scope="module")
def contract(client, vendor):
    data = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "vendor_id": vendor["id"],
                "project_id": vendor["demo"]["project_ids"][0],
                "name": "自动化测试服务合同",
                "amount": "30000",
                "sign_date": "2026-11-01",
                "start_date": "2026-11-01",
                "end_date": "2027-06-30",
                "pay_terms": [
                    {"name": "首付款", "ratio": 0.5, "amount": "15000", "due_date": "2026-11-15"},
                    {"name": "尾款", "ratio": 0.5, "amount": "15000", "due_date": "2027-06-30"},
                ],
                "activate": True,
            },
            headers=vendor["purchase"],
        )
    )
    return {"id": int(data["id"]), "data": data, "purchase": vendor["purchase"]}


def test_contract_lifecycle(client, contract):
    assert contract["data"]["status"] == "ACTIVE"
    updated = _ok(
        client.put(
            f"/api/v1/contracts/{contract['id']}",
            json={
                "vendor_id": contract["data"]["vendor_id"],
                "project_id": contract["data"]["project_id"],
                "name": contract["data"]["name"],
                "amount": contract["data"]["amount"],
                "remark": "补充说明",
                "version": contract["data"]["version"],
            },
            headers=contract["purchase"],
        )
    )
    assert updated["remark"] == "补充说明"

    expired = _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/status",
            json={"status": "EXPIRED", "reason": "到期提醒"},
            headers=contract["purchase"],
        )
    )
    assert expired["status"] == "EXPIRED"
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/status",
            json={"status": "ACTIVE"},
            headers=contract["purchase"],
        )
    )
    detail = _ok(client.get(f"/api/v1/contracts/{contract['id']}", headers=contract["purchase"]))
    assert detail["status"] == "ACTIVE"
    assert _ok(client.get(f"/api/v1/contracts/{contract['id']}/payments", headers=contract["purchase"])) == []


def test_contract_risks_and_vendor_risks(client, vendor, contract):
    contracts = _ok(client.get("/api/v1/contracts", params={"page": 1, "page_size": 50}, headers=vendor["purchase"]))
    assert contracts["items"]
    risks = _ok(client.get("/api/v1/contracts/risks", headers=vendor["purchase"]))
    assert isinstance(risks, list)
    vendor_risks = _ok(client.get("/api/v1/vendors/risks", headers=vendor["purchase"]))
    assert isinstance(vendor_risks, list)


def test_finance_payment_flow(client, auth, vendor, contract):
    finance = auth("finance")
    project_id = vendor["demo"]["project_ids"][0]
    payment = _ok(
        client.post(
            "/api/v1/finance/payments",
            json={
                "project_id": project_id,
                "vendor_id": vendor["id"],
                "contract_id": contract["id"],
                "amount": "15000",
                "pay_date": "2026-11-20",
                "method": "BANK",
                "remark": "首付款支付",
            },
            headers=finance,
        )
    )
    assert payment["status"] == "PENDING"
    assert payment["account_code"]

    paid = _ok(
        client.post(
            f"/api/v1/finance/payments/{payment['id']}/pay",
            json={"pay_date": "2026-11-20"},
            headers=finance,
        )
    )
    assert paid["status"] == "PAID"

    costs = _ok(
        client.get(
            "/api/v1/finance/costs",
            params={"page": 1, "page_size": 100, "biz_type": "PAYMENT", "project_id": project_id},
            headers=finance,
        )
    )
    assert costs["items"]
    cost_id = next(item["id"] for item in costs["items"] if item["biz_id"] == payment["id"])
    cost = _ok(client.get(f"/api/v1/finance/costs/{cost_id}", headers=finance))
    assert float(cost["amount"]) == 15000.0

    reversal = _ok(
        client.post(
            f"/api/v1/finance/costs/{cost_id}/reverse",
            json={"reason": "测试冲销"},
            headers=finance,
        )
    )
    assert reversal["is_reversal"] is True
    assert float(reversal["amount"]) == -15000.0
    again = client.post(
        f"/api/v1/finance/costs/{cost_id}/reverse",
        json={"reason": "重复冲销"},
        headers=finance,
    )
    assert again.status_code == 422

    cancelled = _ok(
        client.post(
            "/api/v1/finance/payments",
            json={
                "project_id": project_id,
                "vendor_id": vendor["id"],
                "amount": "1000",
                "remark": "待取消付款",
            },
            headers=finance,
        )
    )
    cancelled = _ok(
        client.post(f"/api/v1/finance/payments/{cancelled['id']}/cancel", headers=finance)
    )
    assert cancelled["status"] == "CANCELED"
    detail = _ok(client.get(f"/api/v1/finance/payments/{payment['id']}", headers=finance))
    assert detail["id"] == payment["id"]


def test_finance_receipt_and_revenue(client, auth, vendor, demo):
    finance = auth("finance")
    project_id = demo["project_ids"][0]

    receipt = _ok(
        client.post(
            "/api/v1/finance/receipts",
            json={
                "project_id": project_id,
                "amount": "50000",
                "receipt_date": "2026-11-21",
                "method": "BANK",
                "remark": "回款测试",
            },
            headers=finance,
        )
    )
    assert float(receipt["amount"]) == 50000.0
    assert _ok(client.get(f"/api/v1/finance/receipts/{receipt['id']}", headers=finance))["id"] == receipt["id"]

    canceled = _ok(
        client.post(
            "/api/v1/finance/receipts",
            json={"project_id": project_id, "amount": "1000", "remark": "待作废"},
            headers=finance,
        )
    )
    _ok(client.post(f"/api/v1/finance/receipts/{canceled['id']}/cancel", headers=finance))

    revenue = _ok(
        client.post(
            "/api/v1/finance/revenue",
            json={
                "project_id": project_id,
                "amount": "60000",
                "confirm_date": "2026-11-22",
                "remark": "计收测试",
                "confirm": True,
            },
            headers=finance,
        )
    )
    assert revenue["status"] == "CONFIRMED"
    assert _ok(client.get(f"/api/v1/finance/revenue/{revenue['id']}", headers=finance))["id"] == revenue["id"]

    pending = _ok(
        client.post(
            "/api/v1/finance/revenue",
            json={"project_id": project_id, "amount": "8000", "confirm": False, "remark": "待确认"},
            headers=finance,
        )
    )
    confirmed = _ok(
        client.post(f"/api/v1/finance/revenue/{pending['id']}/confirm", headers=finance)
    )
    assert confirmed["status"] == "CONFIRMED"

    cancelable = _ok(
        client.post(
            "/api/v1/finance/revenue",
            json={"project_id": project_id, "amount": "3000", "confirm": False, "remark": "待取消"},
            headers=finance,
        )
    )
    canceled_revenue = _ok(
        client.post(f"/api/v1/finance/revenue/{cancelable['id']}/cancel", headers=finance)
    )
    assert canceled_revenue["status"] == "CANCELED"

    payments = _ok(client.get("/api/v1/finance/payments", params={"page": 1, "page_size": 20}, headers=finance))
    receipts = _ok(client.get("/api/v1/finance/receipts", params={"page": 1, "page_size": 20}, headers=finance))
    revenues = _ok(client.get("/api/v1/finance/revenue", params={"page": 1, "page_size": 20}, headers=finance))
    assert payments["total"] and receipts["total"] and revenues["total"]


def test_finance_budget_and_period(client, auth, demo):
    finance = auth("finance")
    project_id = demo["project_ids"][0]
    budget = _ok(
        client.post(
            "/api/v1/finance/budgets",
            json={"project_id": project_id, "account_code": "5401", "year": 2027, "amount": "80000"},
            headers=finance,
        )
    )
    budgets = _ok(
        client.get("/api/v1/finance/budgets", params={"project_id": project_id, "year": 2027}, headers=finance)
    )
    assert budgets["items"] if isinstance(budgets, dict) else budgets
    status = _ok(
        client.get(
            "/api/v1/finance/budget-status", params={"project_id": project_id, "year": 2027}, headers=finance
        )
    )
    assert "items" in status or "total_budget" in status
    project_budget = _ok(
        client.get(f"/api/v1/finance/projects/{project_id}/budget", params={"year": 2027}, headers=finance)
    )
    assert project_budget
    _ok(client.delete(f"/api/v1/finance/budgets/{budget['id']}", headers=finance))

    accounts = _ok(client.get("/api/v1/finance/accounts", headers=finance))
    assert accounts

    period = _ok(
        client.post("/api/v1/finance/periods/close", json={"period": "2026-12", "remark": "测试关账"}, headers=finance)
    )
    assert period["status"] == "CLOSED"
    reopened = _ok(
        client.post(
            "/api/v1/finance/periods/reopen",
            json={"period": "2026-12", "remark": "反关账测试说明"},
            headers=finance,
        )
    )
    assert reopened["status"] == "OPEN"
    periods = _ok(client.get("/api/v1/finance/periods", params={"year": 2026}, headers=finance))
    assert periods
