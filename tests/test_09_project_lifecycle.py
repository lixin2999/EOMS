"""项目全生命周期：立项审批 → WBS/任务 → 计划确认 → 执行 → 变更 → 验收 → 关闭 → 归档。"""

from __future__ import annotations

import pytest

from tests.helpers import approve_instance, upload_png


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


@pytest.fixture(scope="module")
def flow(client, auth, demo):
    pm = auth("pm")
    manager = auth("manager")
    director = auth("director")
    pm_id = demo["users"]["pm"]

    created = _ok(
        client.post(
            "/api/v1/projects",
            json={
                "name": "生命周期测试项目",
                "type": "IMPLEMENT",
                "manager_id": pm_id,
                "plan_start": "2026-11-01",
                "plan_end": "2026-12-31",
                "budget_amount": "100000",
                "contract_amount": "200000",
                "description": "自动化测试项目",
            },
            headers=pm,
        )
    )
    project_id = int(created["id"])
    assert created["status"] == "DRAFT"

    initiation = _ok(
        client.post(
            "/api/v1/projects/initiations",
            json={
                "project_id": project_id,
                "background": "测试立项背景",
                "goal": "验证项目全流程",
                "estimate_cost": "90000",
                "estimate_income": "180000",
                "submit": True,
            },
            headers=pm,
        )
    )
    approve_instance(client, [manager, director], int(initiation["instance_id"]))

    project = _ok(client.get(f"/api/v1/projects/{project_id}", headers=pm))
    assert project["status"] == "ACTIVE"

    wbs_root = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/wbs",
            json={"name": "实施阶段", "plan_start": "2026-11-01", "plan_end": "2026-12-20"},
            headers=pm,
        )
    )
    wbs_child = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/wbs",
            json={"name": "开发任务包", "parent_id": wbs_root["id"], "progress": 10},
            headers=pm,
        )
    )
    _ok(
        client.put(
            f"/api/v1/projects/wbs/{wbs_child['id']}",
            json={"progress": 60, "owner_id": pm_id},
            headers=pm,
        )
    )

    task = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/tasks",
            json={
                "name": "接口开发",
                "wbs_id": wbs_child["id"],
                "owner_id": pm_id,
                "plan_start": "2026-11-02",
                "plan_end": "2026-11-30",
                "status": "DOING",
                "priority": "HIGH",
                "estimate_hours": "16",
            },
            headers=pm,
        )
    )
    extra_task = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/tasks",
            json={"name": "临时任务", "status": "TODO"},
            headers=pm,
        )
    )
    _ok(client.delete(f"/api/v1/projects/tasks/{extra_task['id']}", headers=pm))

    milestone = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/milestones",
            json={"name": "联调完成", "plan_date": "2026-11-28"},
            headers=pm,
        )
    )
    _ok(
        client.post(
            f"/api/v1/projects/milestones/{milestone['id']}/complete",
            json={"actual_date": "2026-11-27"},
            headers=pm,
        )
    )

    _ok(client.post(f"/api/v1/projects/{project_id}/confirm-plan", headers=pm))
    _ok(client.post(f"/api/v1/projects/{project_id}/start-execution", headers=pm))

    change = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/changes",
            json={"type": "BUDGET", "after": {"budget_amount": "120000"}, "reason": "需求增加追加预算"},
            headers=pm,
        )
    )
    approve_instance(client, [manager, director], int(change["instance_id"]))
    changed = _ok(client.get(f"/api/v1/projects/{project_id}", headers=pm))
    assert float(changed["budget_amount"]) == 120000.0

    issue = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/issues",
            json={"title": "接口联调延迟", "level": "HIGH", "owner_id": pm_id},
            headers=pm,
        )
    )
    _ok(
        client.post(
            f"/api/v1/projects/{project_id}/risks",
            json={"title": "供应商交付风险", "level": "MEDIUM", "owner_id": pm_id},
            headers=pm,
        )
    )
    _ok(
        client.post(
            f"/api/v1/projects/{project_id}/reports",
            json={
                "type": "WEEKLY",
                "period": "2026-W47",
                "progress": 60,
                "content": "本周完成接口开发并提交测试环境",
                "next_plan": "下周联调",
            },
            headers=pm,
        )
    )

    invoice = upload_png(client, pm, "acceptance.png")
    acceptance = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/acceptances",
            json={
                "acceptor": "客户代表",
                "result": "PASS",
                "sign_file_id": invoice,
                "accept_amount": "180000",
                "remark": "验收通过",
            },
            headers=pm,
        )
    )
    approve_instance(client, [manager, director], int(acceptance["instance_id"]))

    _ok(
        client.put(
            f"/api/v1/projects/tasks/{task['id']}",
            json={"status": "DONE", "progress": 100, "actual_hours": "18"},
            headers=pm,
        )
    )
    _ok(
        client.put(
            f"/api/v1/projects/issues/{issue['id']}",
            json={"status": "CLOSED", "solution": "已补充资源完成联调"},
            headers=pm,
        )
    )

    check = _ok(client.get(f"/api/v1/projects/{project_id}/close-check", headers=pm))
    closed = _ok(
        client.post(
            f"/api/v1/projects/{project_id}/close",
            json={"force": False},
            headers=pm,
        )
    )
    archived = _ok(client.post(f"/api/v1/projects/{project_id}/archive", headers=pm))
    archives = _ok(client.get(f"/api/v1/projects/{project_id}/archives", headers=pm))

    return {
        "pm": pm,
        "manager": manager,
        "director": director,
        "project_id": project_id,
        "task_id": task["id"],
        "wbs_id": wbs_root["id"],
        "milestone_id": milestone["id"],
        "issue_id": issue["id"],
        "acceptance_id": acceptance["id"],
        "close_check": check,
        "closed": closed,
        "archived": archived,
        "archives": archives,
    }


def test_wbs_tree_and_tasks(client, flow):
    wbs = _ok(client.get(f"/api/v1/projects/{flow['project_id']}/wbs", headers=flow["pm"]))
    assert wbs["items"]
    tree = wbs["tree"]
    assert tree and tree[0]["name"] == "实施阶段"
    assert tree[0]["children"][0]["name"] == "开发任务包"

    tasks = _ok(client.get(f"/api/v1/projects/{flow['project_id']}/tasks", headers=flow["pm"]))
    assert len(tasks) == 1
    assert tasks[0]["status"] == "DONE"


def test_milestone_completed(client, flow):
    items = _ok(
        client.get(f"/api/v1/projects/{flow['project_id']}/milestones", headers=flow["pm"])
    )
    row = next(item for item in items if item["id"] == flow["milestone_id"])
    assert row["status"] == "DONE"
    assert row["actual_date"] == "2026-11-27"


def test_baseline_and_deviation_available(client, flow):
    baseline = _ok(
        client.get(f"/api/v1/projects/{flow['project_id']}/baseline", headers=flow["pm"])
    )
    assert baseline
    deviation = _ok(
        client.get(f"/api/v1/projects/{flow['project_id']}/deviation", headers=flow["pm"])
    )
    assert "completion_rate" in deviation
    assert deviation["task_total"] >= 1


def test_project_reports_issues_and_risks(client, flow):
    reports = _ok(
        client.get(f"/api/v1/projects/{flow['project_id']}/reports", headers=flow["pm"])
    )
    assert any(item["period"] == "2026-W47" for item in reports)

    risks = _ok(client.get(f"/api/v1/projects/{flow['project_id']}/risks", headers=flow["pm"]))
    assert risks and risks[0]["status"] in {"OPEN", "TRACKING", "CLOSED"}

    issues = _ok(client.get(f"/api/v1/projects/{flow['project_id']}/issues", headers=flow["pm"]))
    assert issues and issues[0]["status"] == "CLOSED"


def test_acceptance_approved_with_archive(client, flow):
    detail = _ok(
        client.get(f"/api/v1/projects/acceptances/{flow['acceptance_id']}", headers=flow["pm"])
    )
    assert detail["status"] == "APPROVED"
    assert detail["sign_file"]["id"]


def test_close_and_archive(client, flow):
    assert flow["close_check"]["can_close"] is True
    assert flow["closed"]["status"] == "CLOSED"
    assert flow["archived"]["status"] == "ARCHIVED"
    assert any(item["doc_type"] == "ACCEPTANCE" for item in flow["archives"])


def test_project_pnl_and_finance_summary(client, flow):
    pnl = _ok(
        client.get(f"/api/v1/projects/{flow['project_id']}/pnl", headers=flow["pm"])
    )
    assert "revenue" in pnl and "cost" in pnl
    summary = _ok(
        client.get(f"/api/v1/finance/projects/{flow['project_id']}/summary", headers=flow["pm"])
    )
    assert "cost" in summary or "total" in summary


def test_update_closed_project_rejected(client, flow):
    response = client.put(
        f"/api/v1/projects/{flow['project_id']}",
        json={"name": "关闭后改名", "version": 1},
        headers=flow["pm"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == 3000
