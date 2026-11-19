"""请假/发文/报销的完整审批与后续处理，以及通知、文件、元数据、看板、报表。"""

from __future__ import annotations

import pytest

from tests.helpers import approve_instance, expense_payload, pending_task, upload_png


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _pm_project_id(client, headers) -> int:
    data = _ok(
        client.get("/api/v1/projects", params={"page": 1, "page_size": 50}, headers=headers)
    )
    assert data["items"]
    for item in data["items"]:
        if item.get("status") == "ACTIVE":
            return int(item["id"])
    return int(data["items"][0]["id"])


# ------------------------------------------------------------------ 请假
@pytest.fixture(scope="module")
def leave(client, auth, demo):
    employee = auth("employee")
    leader = auth("leader")
    manager = auth("manager")

    created = _ok(
        client.post(
            "/api/v1/approvals/leaves",
            json={
                "type": "ANNUAL",
                "start_time": "2026-12-01T09:00:00",
                "end_time": "2026-12-02T18:00:00",
                "duration": "2",
                "reason": "年度休假安排",
                "handover_user_id": demo["users"]["leader"],
            },
            headers=employee,
        )
    )
    leave_id = int(created["id"])
    assert created["status"] == "DRAFT"

    submitted = _ok(
        client.post(f"/api/v1/approvals/leaves/{leave_id}/submit", headers=employee)
    )
    assert submitted["status"] == "RUNNING"
    instance_id = int(submitted["instance_id"])

    # 催办：发起人可对当前待办催办
    _ok(
        client.post(
            f"/api/v1/workflow/instances/{instance_id}/actions",
            json={"action": "URGE", "comment": "请尽快审批"},
            headers=employee,
        )
    )

    withdrawn = _ok(
        client.post(f"/api/v1/approvals/leaves/{leave_id}/withdraw", headers=employee)
    )
    assert withdrawn["status"] == "DRAFT"

    resubmitted = _ok(
        client.post(f"/api/v1/approvals/leaves/{leave_id}/submit", headers=employee)
    )
    assert resubmitted["status"] == "RUNNING"
    instance_id = int(resubmitted["instance_id"])

    handled = approve_instance(client, [leader, manager], instance_id)
    assert handled >= 2
    detail = _ok(client.get(f"/api/v1/approvals/leaves/{leave_id}", headers=employee))
    return {
        "id": leave_id,
        "employee": employee,
        "leader": leader,
        "manager": manager,
        "instance_id": instance_id,
        "detail": detail,
    }


def test_leave_approved_and_balance_deducted(client, leave):
    assert leave["detail"]["status"] == "APPROVED"
    balances = _ok(
        client.get("/api/v1/approvals/leaves/balance", params={"year": 2026}, headers=leave["employee"])
    )
    annual = next(item for item in balances if item["type"] == "ANNUAL")
    assert float(annual["remain"]) == 5.0


def test_leave_rejected_then_canceled(client, auth):
    employee = auth("employee")
    leader = auth("leader")
    created = _ok(
        client.post(
            "/api/v1/approvals/leaves",
            json={
                "type": "PERSONAL",
                "start_time": "2026-12-10T09:00:00",
                "end_time": "2026-12-10T18:00:00",
                "duration": "1",
                "reason": "个人事务",
            },
            headers=employee,
        )
    )
    leave_id = int(created["id"])
    submitted = _ok(
        client.post(f"/api/v1/approvals/leaves/{leave_id}/submit", headers=employee)
    )
    instance_id = int(submitted["instance_id"])

    task = pending_task(client, leader, instance_id)
    assert task is not None
    _ok(
        client.post(
            f"/api/v1/workflow/instances/{instance_id}/actions",
            json={"action": "REJECT", "task_id": task["id"], "comment": "工作安排冲突"},
            headers=leader,
        )
    )
    detail = _ok(client.get(f"/api/v1/approvals/leaves/{leave_id}", headers=employee))
    assert detail["status"] == "REJECTED"

    canceled = _ok(
        client.post(f"/api/v1/approvals/leaves/{leave_id}/cancel", headers=employee)
    )
    assert canceled["status"] == "CANCELED"


def test_leave_validation_rejects_bad_payload(client, auth):
    employee = auth("employee")
    bad_duration = client.post(
        "/api/v1/approvals/leaves",
        json={
            "type": "PERSONAL",
            "start_time": "2026-12-20T09:00:00",
            "end_time": "2026-12-21T18:00:00",
            "duration": "5",
            "reason": "时长不匹配",
        },
        headers=employee,
    )
    assert bad_duration.status_code == 422
    assert bad_duration.json()["code"] == 3000

    bad_type = client.post(
        "/api/v1/approvals/leaves",
        json={
            "type": "VACATION",
            "start_time": "2026-12-20T09:00:00",
            "end_time": "2026-12-20T18:00:00",
            "duration": "1",
        },
        headers=employee,
    )
    assert bad_type.status_code == 422


# ------------------------------------------------------------------ 发文
@pytest.fixture(scope="module")
def document(client, auth):
    employee = auth("employee")
    leader = auth("leader")
    manager = auth("manager")

    created = _ok(
        client.post(
            "/api/v1/approvals/documents",
            json={
                "title": "关于开展年度安全检查的通知",
                "category": "DISPATCH",
                "secret_level": "INTERNAL",
                "content": "请各部门按要求完成年度安全检查并提交报告。",
                "effect_date": "2026-12-01",
            },
            headers=employee,
        )
    )
    doc_id = int(created["id"])
    assert created["status"] == "DRAFT"

    submitted = _ok(
        client.post(f"/api/v1/approvals/documents/{doc_id}/submit", headers=employee)
    )
    instance_id = int(submitted["instance_id"])

    withdrawn = _ok(
        client.post(f"/api/v1/approvals/documents/{doc_id}/withdraw", headers=employee)
    )
    assert withdrawn["status"] == "DRAFT"

    submitted = _ok(
        client.post(f"/api/v1/approvals/documents/{doc_id}/submit", headers=employee)
    )
    instance_id = int(submitted["instance_id"])
    approve_instance(client, [leader, manager], instance_id)
    detail = _ok(client.get(f"/api/v1/approvals/documents/{doc_id}", headers=employee))
    return {"id": doc_id, "employee": employee, "detail": detail, "instance_id": instance_id}


def test_document_approved_with_detail(client, document):
    assert document["detail"]["status"] == "APPROVED"
    assert document["detail"]["creator_name"]
    documents = _ok(
        client.get(
            "/api/v1/approvals/documents",
            params={"page": 1, "page_size": 50, "category": "DISPATCH"},
            headers=document["employee"],
        )
    )
    assert any(item["id"] == document["id"] for item in documents["items"])


def test_document_requires_attachment_for_seal(client, auth):
    employee = auth("employee")
    created = _ok(
        client.post(
            "/api/v1/approvals/documents",
            json={
                "title": "用印申请",
                "category": "SEAL",
                "secret_level": "SECRET",
                "content": "合同用印",
            },
            headers=employee,
        )
    )
    doc_id = int(created["id"])
    rejected = client.post(f"/api/v1/approvals/documents/{doc_id}/submit", headers=employee)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == 3000
    _ok(client.post(f"/api/v1/approvals/documents/{doc_id}/cancel", headers=employee))


def test_document_update_and_invalid_category(client, auth):
    employee = auth("employee")
    created = _ok(
        client.post(
            "/api/v1/approvals/documents",
            json={"title": "制度文件草稿", "category": "INSTITUTION", "content": "制度内容"},
            headers=employee,
        )
    )
    doc_id = int(created["id"])
    updated = _ok(
        client.put(
            f"/api/v1/approvals/documents/{doc_id}",
            json={"title": "制度文件（修订）", "version": created["version"]},
            headers=employee,
        )
    )
    assert updated["title"] == "制度文件（修订）"

    conflict = client.put(
        f"/api/v1/approvals/documents/{doc_id}",
        json={"title": "过期版本修改", "version": created["version"]},
        headers=employee,
    )
    assert conflict.status_code == 409

    bad = client.post(
        "/api/v1/approvals/documents",
        json={"title": "非法分类", "category": "UNKNOWN", "content": "x"},
        headers=employee,
    )
    assert bad.status_code == 422
    _ok(client.post(f"/api/v1/approvals/documents/{doc_id}/cancel", headers=employee))


# ------------------------------------------------------------------ 报销全流程
@pytest.fixture(scope="module")
def expense(client, auth, demo):
    pm = auth("pm")
    manager = auth("manager")
    finance = auth("finance")
    project_id = _pm_project_id(client, pm)
    invoice_id = upload_png(client, pm, "reimburse.png")

    payload = expense_payload(project_id, "报销全流程测试", amount="120.00")
    payload["invoices_file_ids"] = [invoice_id]
    created = _ok(client.post("/api/v1/approvals/expenses", json=payload, headers=pm))
    expense_id = int(created["id"])

    updated = _ok(
        client.put(
            f"/api/v1/approvals/expenses/{expense_id}",
            json={
                "project_id": project_id,
                "type": "TRAVEL",
                "items": [
                    {
                        "category": "TRAVEL",
                        "amount": "120.00",
                        "occur_date": "2026-11-15",
                        "description": "报销全流程测试",
                    }
                ],
                "invoices_file_ids": [invoice_id],
                "remark": "报销全流程测试",
                "version": created["version"],
            },
            headers=pm,
        )
    )
    assert updated["remark"] == "报销全流程测试"

    submitted = _ok(
        client.post(f"/api/v1/approvals/expenses/{expense_id}/submit", headers=pm)
    )
    instance_id = int(submitted["instance_id"])

    # 抄送财务
    _ok(
        client.post(
            f"/api/v1/workflow/instances/{instance_id}/actions",
            json={"action": "CC", "cc_user_ids": [demo["users"]["finance"]]},
            headers=pm,
        )
    )

    withdrawn = _ok(
        client.post(f"/api/v1/approvals/expenses/{expense_id}/withdraw", headers=pm)
    )
    assert withdrawn["status"] == "DRAFT"

    submitted = _ok(
        client.post(f"/api/v1/approvals/expenses/{expense_id}/submit", headers=pm)
    )
    instance_id = int(submitted["instance_id"])
    approve_instance(client, [manager], instance_id)
    approved = _ok(client.get(f"/api/v1/approvals/expenses/{expense_id}", headers=pm))
    assert approved["status"] == "APPROVED"

    verified = _ok(
        client.post(f"/api/v1/approvals/expenses/{expense_id}/verify", headers=finance)
    )
    assert verified["status"] == "VERIFIED"

    payment = _ok(
        client.post(
            "/api/v1/finance/payments",
            json={
                "project_id": project_id,
                "expense_id": expense_id,
                "amount": "120.00",
                "pay_date": "2026-11-25",
                "method": "BANK",
                "remark": "报销付款",
            },
            headers=finance,
        )
    )
    _ok(
        client.post(
            f"/api/v1/finance/payments/{payment['id']}/pay",
            json={"pay_date": "2026-11-25"},
            headers=finance,
        )
    )
    archived = _ok(
        client.post(f"/api/v1/approvals/expenses/{expense_id}/archive", headers=finance)
    )
    assert archived["status"] == "ARCHIVED"
    return {"id": expense_id, "pm": pm, "finance": finance, "project_id": project_id}


def test_expense_cancel_draft(client, expense):
    created = _ok(
        client.post(
            "/api/v1/approvals/expenses",
            json={
                "project_id": expense["project_id"],
                "type": "OFFICE",
                "items": [{"category": "OFFICE", "amount": "30.00", "occur_date": "2026-11-16"}],
                "remark": "待取消报销",
            },
            headers=expense["pm"],
        )
    )
    canceled = _ok(
        client.post(f"/api/v1/approvals/expenses/{created['id']}/cancel", headers=expense["pm"])
    )
    assert canceled["status"] == "CANCELED"


def test_expense_reject_and_resubmit_blocked(client, auth, expense):
    pm = auth("pm")
    manager = auth("manager")
    invoice_id = upload_png(client, pm, "reject.png")
    payload = expense_payload(expense["project_id"], "驳回报销测试", amount="60.00")
    payload["invoices_file_ids"] = [invoice_id]
    created = _ok(client.post("/api/v1/approvals/expenses", json=payload, headers=pm))
    submitted = _ok(
        client.post(f"/api/v1/approvals/expenses/{created['id']}/submit", headers=pm)
    )
    instance_id = int(submitted["instance_id"])
    task = pending_task(client, manager, instance_id)
    assert task is not None
    _ok(
        client.post(
            f"/api/v1/workflow/instances/{instance_id}/actions",
            json={"action": "REJECT", "task_id": task["id"], "comment": "发票不合规"},
            headers=manager,
        )
    )
    rejected = _ok(
        client.get(f"/api/v1/approvals/expenses/{created['id']}", headers=pm)
    )
    assert rejected["status"] == "REJECTED"

    duplicate_submit = client.post(
        f"/api/v1/approvals/expenses/{created['id']}/submit", headers=pm
    )
    assert duplicate_submit.status_code == 200
    assert duplicate_submit.json()["data"]["status"] == "RUNNING"

    detail = _ok(client.get(f"/api/v1/approvals/expenses/{expense['id']}", headers=pm))
    assert detail["status"] == "ARCHIVED"


# ------------------------------------------------------------------ 通知
def test_notifications_list_and_mark_read(client, auth):
    pm = auth("pm")
    data = _ok(
        client.get("/api/v1/notifications", params={"page": 1, "page_size": 50}, headers=pm)
    )
    assert data["total"] >= 1
    assert data["items"]
    unread = _ok(client.get("/api/v1/notifications/unread-count", headers=pm))
    assert "count" in unread

    target = data["items"][0]["id"]
    _ok(client.post(f"/api/v1/notifications/{target}/read", headers=pm))
    _ok(client.post("/api/v1/notifications/read", json={"ids": [target]}, headers=pm))
    all_read = _ok(client.post("/api/v1/notifications/read", json={"all": True}, headers=pm))
    assert all_read["count"] >= 0
    remaining = _ok(client.get("/api/v1/notifications/unread-count", headers=pm))
    assert remaining["count"] == 0


# ------------------------------------------------------------------ 文件
def test_file_upload_download_delete(client, auth, demo):
    pm = auth("pm")
    file_id = upload_png(client, pm, "meta-test.png")
    detail = _ok(client.get(f"/api/v1/files/{file_id}", headers=pm))
    assert detail["size"] > 0
    assert detail["download_url"].endswith("/download")

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.iam import SysFile

    with SessionLocal() as db:
        key = db.execute(select(SysFile.path).where(SysFile.id == file_id)).scalar_one()

    downloaded = client.get(f"/api/v1/files/{file_id}/download", headers=pm)
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"\x89PNG")

    by_key = client.get("/api/v1/files/download", params={"key": key}, headers=pm)
    assert by_key.status_code == 200

    listing = _ok(
        client.get(
            "/api/v1/files",
            params={"page": 1, "page_size": 20, "keyword": "meta-test", "mine": True},
            headers=pm,
        )
    )
    assert any(item["id"] == file_id for item in listing["items"])

    employee = auth("employee")
    assert client.get(f"/api/v1/files/{file_id}", headers=employee).status_code == 200
    forbidden_delete = client.delete(f"/api/v1/files/{file_id}", headers=employee)
    assert forbidden_delete.status_code == 403
    assert forbidden_delete.json()["code"] == 1003

    _ok(client.delete(f"/api/v1/files/{file_id}", headers=pm))
    gone = client.get(f"/api/v1/files/{file_id}", headers=pm)
    assert gone.status_code == 404


def test_file_storage_health(client, admin_headers):
    data = _ok(client.get("/api/v1/files/storage/health", headers=admin_headers))
    assert data["backend"] in {"local", "minio"}


# ------------------------------------------------------------------ 元数据 / 看板 / 报表
def test_meta_endpoints(client, auth):
    pm = auth("pm")
    enums = _ok(client.get("/api/v1/meta/enums", headers=pm))
    assert enums["enums"] and enums["labels"]
    options = _ok(
        client.get("/api/v1/meta/options", params={"keyword": "经"}, headers=pm)
    )
    assert "users" in options and "projects" in options and "depts" in options
    dicts = _ok(client.get("/api/v1/meta/dicts", params={"dict_type": "expense_type"}, headers=pm))
    assert dicts.get("expense_type")
    me = _ok(client.get("/api/v1/meta/me", headers=pm))
    assert me["username"] == "pm"


def test_dashboard_endpoints(client, auth):
    pm = auth("pm")
    dashboard = _ok(client.get("/api/v1/dashboard", headers=pm))
    assert dashboard
    overview = _ok(client.get("/api/v1/dashboard/overview", params={"year": 2026}, headers=pm))
    assert overview
    health = _ok(client.get("/api/v1/dashboard/health", params={"limit": 5}, headers=pm))
    assert health
    alerts = _ok(client.get("/api/v1/dashboard/alerts", params={"days": 60}, headers=pm))
    assert alerts


def test_reports_catalog_and_payload(client, auth):
    finance = auth("finance")
    catalog = _ok(client.get("/api/v1/reports/catalog", headers=finance))
    codes = {item["code"] for item in catalog}
    assert {"PROJECT_PNL", "REVENUE", "CASHFLOW"} <= codes

    for code in ("PROJECT_PNL", "REVENUE", "CASHFLOW", "APPROVAL_EFFICIENCY"):
        payload = _ok(client.get(f"/api/v1/reports/{code}", headers=finance))
        assert payload


def test_reports_snapshot_and_export(client, auth):
    finance = auth("finance")
    generated = _ok(
        client.post("/api/v1/reports/snapshots/generate", params={"period": "2026-11"}, headers=finance)
    )
    assert generated["count"] >= 1
    snapshots = _ok(
        client.get("/api/v1/reports/snapshots", params={"limit": 10}, headers=finance)
    )
    assert snapshots
    latest = _ok(
        client.get("/api/v1/reports/snapshots/PROJECT_PNL", params={"period": "2026-11"}, headers=finance)
    )
    assert latest["report_code"] == "PROJECT_PNL"

    excel = client.get(
        "/api/v1/reports/PROJECT_PNL/export", params={"format": "excel"}, headers=finance
    )
    assert excel.status_code == 200
    assert excel.content[:2] == b"PK"
    pdf = client.get(
        "/api/v1/reports/PROJECT_PNL/export", params={"format": "pdf"}, headers=finance
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    denied = client.get("/api/v1/reports/PROJECT_PNL/export", headers=auth("employee"))
    assert denied.status_code == 403
