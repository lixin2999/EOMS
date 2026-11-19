"""幂等键：同一 Idempotency-Key 重放首次结果，不重复落库。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.approval import Expense


def _payload(project_id: int, remark: str) -> dict:
    return {
        "project_id": project_id,
        "type": "TRAVEL",
        "items": [
            {
                "category": "TRAVEL",
                "amount": "88.88",
                "occur_date": "2026-12-10",
                "description": "幂等测试",
            }
        ],
        "remark": remark,
    }


def _expense_count(remark: str) -> int:
    with SessionLocal() as db:
        return int(db.execute(select(func.count(Expense.id)).where(Expense.remark == remark)).scalar_one())


def test_idempotency_key_replays_first_response(client, auth, demo):
    project_id = sorted(demo["project_ids"])[0]
    remark = f"idem-{uuid.uuid4().hex[:8]}"
    key = uuid.uuid4().hex
    headers = {**auth("director"), "Idempotency-Key": key}

    first = client.post("/api/v1/approvals/expenses", json=_payload(project_id, remark), headers=headers)
    assert first.status_code == 200, first.text
    expense_id = first.json()["data"]["id"]

    second = client.post("/api/v1/approvals/expenses", json=_payload(project_id, remark), headers=headers)
    assert second.status_code == 200
    assert second.json()["data"]["id"] == expense_id
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert _expense_count(remark) == 1


def test_without_idempotency_key_creates_twice(client, auth, demo):
    project_id = sorted(demo["project_ids"])[0]
    remark = f"dup-{uuid.uuid4().hex[:8]}"
    first = client.post("/api/v1/approvals/expenses", json=_payload(project_id, remark), headers=auth("director"))
    second = client.post("/api/v1/approvals/expenses", json=_payload(project_id, remark), headers=auth("director"))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert _expense_count(remark) == 2


def test_different_idempotency_key_creates_new_record(client, auth, demo):
    project_id = sorted(demo["project_ids"])[0]
    remark = f"key-{uuid.uuid4().hex[:8]}"
    first = client.post(
        "/api/v1/approvals/expenses",
        json=_payload(project_id, remark),
        headers={**auth("director"), "Idempotency-Key": uuid.uuid4().hex},
    )
    second = client.post(
        "/api/v1/approvals/expenses",
        json=_payload(project_id, remark),
        headers={**auth("director"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert _expense_count(remark) == 2
