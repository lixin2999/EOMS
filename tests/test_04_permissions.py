"""权限与认证边界：未登录、无权限、越权写操作。"""

from __future__ import annotations


def test_missing_token_returns_401(client):
    assert client.get("/api/v1/projects").status_code == 401


def test_employee_cannot_read_user_admin(client, auth):
    response = client.get("/api/v1/iam/users", headers=auth("employee"))
    assert response.status_code == 403
    assert response.json()["code"] == 1003


def test_employee_cannot_access_finance(client, auth):
    for path in ("/api/v1/finance/payments", "/api/v1/finance/costs", "/api/v1/finance/budgets"):
        response = client.get(path, headers=auth("employee"))
        assert response.status_code == 403, path


def test_director_cannot_manage_users_or_workflow_definition(client, auth):
    assert client.get("/api/v1/iam/users", headers=auth("director")).status_code == 403
    payload = {
        "code": "EXPENSE",
        "name": "越权流程",
        "nodes_json": {"nodes": [{"code": "START", "name": "开始", "type": "START"}]},
    }
    response = client.post("/api/v1/workflow/definitions", json=payload, headers=auth("director"))
    assert response.status_code == 403


def test_employee_cannot_create_project(client, auth):
    payload = {"name": "越权项目", "type": "OTHER", "manager_id": 1}
    response = client.post("/api/v1/projects", json=payload, headers=auth("employee"))
    assert response.status_code == 403


def test_third_party_cannot_read_audit_logs(client, auth):
    assert client.get("/api/v1/iam/audit-logs", headers=auth("pm")).status_code == 403
    assert client.get("/api/v1/iam/audit-logs", headers=auth("director")).status_code == 200
