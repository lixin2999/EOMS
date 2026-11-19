"""核心业务闭环：报销提交 → 四级审批 → 计入成本。"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.approval import Expense
from app.models.finance import CostRecord

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5b0000000049454e44ae426082"
)


def _upload_invoice(client, headers) -> int:
    response = client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _pm_project_id(client, headers) -> int:
    data = client.get("/api/v1/projects", params={"page": 1, "page_size": 50}, headers=headers).json()["data"]
    assert data["items"], "项目经理至少应能看到一个项目"
    return int(data["items"][0]["id"])


def _pending_task(client, headers, instance_id: int) -> dict | None:
    response = client.get(
        "/api/v1/workflow/tasks",
        params={"status": "PENDING", "mine": "true", "page": 1, "page_size": 100},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    for item in response.json()["data"]["items"]:
        if int(item.get("instance_id") or item.get("instance", {}).get("id") or 0) == instance_id:
            return item
    return None


def _expense_status(expense_id: int) -> str:
    with SessionLocal() as db:
        return db.get(Expense, expense_id).status


def test_expense_approval_end_to_end(client, auth, demo):
    pm_auth = auth("pm")
    manager_auth = auth("manager")
    project_id = _pm_project_id(client, pm_auth)
    invoice_id = _upload_invoice(client, pm_auth)

    created = client.post(
        "/api/v1/approvals/expenses",
        json={
            "project_id": project_id,
            "type": "TRAVEL",
            "items": [
                {
                    "category": "TRAVEL",
                    "amount": "200.00",
                    "occur_date": "2026-12-12",
                    "description": "端到端审批测试",
                }
            ],
            "invoices_file_ids": [invoice_id],
            "payee": "张项目经理",
            "remark": "e2e-approval",
        },
        headers=pm_auth,
    )
    assert created.status_code == 200, created.text
    expense_id = int(created.json()["data"]["id"])

    submitted = client.post(f"/api/v1/approvals/expenses/{expense_id}/submit", headers=pm_auth)
    assert submitted.status_code == 200, submitted.text
    expense = submitted.json()["data"]
    instance_id = int(expense.get("instance_id") or 0)
    assert instance_id > 0, "提交报销应生成流程实例"
    assert expense["status"] in {"RUNNING", "SUBMITTED", "APPROVING"}

    approvals = 0
    for _ in range(5):
        task = _pending_task(client, manager_auth, instance_id)
        if task is None:
            break
        acted = client.post(
            f"/api/v1/workflow/instances/{instance_id}/actions",
            json={"action": "APPROVE", "task_id": task["id"], "comment": "同意"},
            headers=manager_auth,
        )
        assert acted.status_code == 200, acted.text
        approvals += 1

    assert approvals >= 1, "部门负责人/经理应收到并处理审批任务"
    assert _expense_status(expense_id) == "APPROVED"

    with SessionLocal() as db:
        records = (
            db.execute(
                select(CostRecord).where(
                    CostRecord.biz_type == "EXPENSE",
                    CostRecord.biz_id == expense_id,
                )
            )
            .scalars()
            .all()
        )
    assert records, "审批通过后应写入报销成本记录"
    assert float(records[0].amount) == 200.0
    assert records[0].period == "2026-12"


def test_expense_submit_requires_invoice(client, auth):
    headers = auth("pm")
    project_id = _pm_project_id(client, headers)
    created = client.post(
        "/api/v1/approvals/expenses",
        json={
            "project_id": project_id,
            "type": "OFFICE",
            "items": [{"category": "OFFICE", "amount": "10.00", "occur_date": "2026-12-12"}],
            "remark": "no-invoice",
        },
        headers=headers,
    )
    assert created.status_code == 200
    expense_id = created.json()["data"]["id"]
    submitted = client.post(f"/api/v1/approvals/expenses/{expense_id}/submit", headers=headers)
    assert submitted.status_code == 422, submitted.text
    assert submitted.json()["code"] == 3000
