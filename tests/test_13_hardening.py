"""V1.0.1 加固回归：付款/成本幂等、待补记成本、报表口径、Cookie/CSRF、CC 节点。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.cache import cache
from app.core.errors import UnauthorizedError
from app.core.scope import ScopeContext
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.finance import CostRecord, Payment, PendingCost
from app.models.iam import AuditLog, User
from app.models.platform import Notification
from app.models.project import Change, Project, Task
from app.models.vendor import Contract, VendorProject
from app.models.workflow import (
    WorkflowCc,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowRecord,
    WorkflowTask,
)
from app.services.cost.pending import post_pending_costs
from app.services.iam import auth as auth_service
from app.services.project import project as project_service
from app.services.report import export as export_service
from app.services.report import metrics as metrics_service
from app.workflow import engine
from tests.helpers import approve_instance, upload_png

DEMO_PASSWORD = "Eoms@2026"


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _pm_project_id(client, headers) -> int:
    data = _ok(client.get("/api/v1/projects", params={"page": 1, "page_size": 50}, headers=headers))
    assert data["items"]
    for item in data["items"]:
        if item.get("status") == "ACTIVE":
            return int(item["id"])
    return int(data["items"][0]["id"])


def _super_ctx(company_id: int) -> ScopeContext:
    return ScopeContext(user_id=0, company_id=company_id, dept_id=None, is_super=True, scopes={"ALL"})


def _login_payload(username: str) -> dict:
    data = auth_service.create_captcha()
    captcha_id = data["captcha_id"]
    return {
        "username": username,
        "password": DEMO_PASSWORD,
        "captcha_id": captcha_id,
        "captcha_code": cache.get(f"captcha:{captcha_id}") or "",
    }


# ------------------------------------------------------------ 1/2. 关账后的成本暂存与补记
@pytest.fixture(scope="module")
def pending_cost_flow(client, auth, demo) -> dict:
    """期间关账后审批照常完成，成本进入 fin_pending_cost（尚未补记）。"""
    pm = auth("pm")
    manager = auth("manager")
    finance = auth("finance")
    project_id = _pm_project_id(client, pm)

    invoice_id = upload_png(client, pm, "hardening.png")
    created = _ok(
        client.post(
            "/api/v1/approvals/expenses",
            json={
                "project_id": project_id,
                "type": "TRAVEL",
                "items": [
                    {
                        "category": "TRAVEL",
                        "amount": "88.00",
                        "occur_date": "2027-03-10",
                        "description": "关账期间报销",
                    }
                ],
                "invoices_file_ids": [invoice_id],
                "remark": "pending-cost-hardening",
            },
            headers=pm,
        )
    )
    expense_id = int(created["id"])
    submitted = _ok(client.post(f"/api/v1/approvals/expenses/{expense_id}/submit", headers=pm))
    instance_id = int(submitted["instance_id"])

    # 审批进行中期间关账：审批动作不应被阻断，成本改为暂存
    closed = _ok(
        client.post("/api/v1/finance/periods/close", json={"period": "2027-03"}, headers=finance)
    )
    assert closed["period"] == "2027-03"

    assert approve_instance(client, [manager], instance_id) >= 1
    approved = _ok(client.get(f"/api/v1/approvals/expenses/{expense_id}", headers=pm))

    with SessionLocal() as db:
        pending = list(
            db.execute(
                select(PendingCost).where(
                    PendingCost.biz_type == "EXPENSE", PendingCost.biz_id == expense_id
                )
            )
            .scalars()
            .all()
        )
        costs = list(
            db.execute(
                select(CostRecord).where(
                    CostRecord.biz_type == "EXPENSE", CostRecord.biz_id == expense_id
                )
            )
            .scalars()
            .all()
        )
        statuses = [row.status for row in pending]

    return {
        "company_id": demo["company_id"],
        "project_id": project_id,
        "expense_id": expense_id,
        "finance": finance,
        "expense_status": approved["status"],
        "pending_count": len(pending),
        "pending_status": statuses,
        "cost_count": len(costs),
    }


def test_approval_completes_while_period_closed(client, pending_cost_flow):
    assert pending_cost_flow["expense_status"] == "APPROVED", "关账不应阻断审批动作"
    assert pending_cost_flow["pending_count"] >= 1, "成本应写入暂存表"
    assert set(pending_cost_flow["pending_status"]) == {"PENDING"}
    assert pending_cost_flow["cost_count"] == 0, "期间关账时不应写入成本台账"

    listing = _ok(
        client.get(
            "/api/v1/finance/pending-costs",
            params={"limit": 100},
            headers=pending_cost_flow["finance"],
        )
    )
    assert any(int(item["biz_id"]) == pending_cost_flow["expense_id"] for item in listing["items"])
    assert "2027-03" in listing["periods"]


def test_reopen_period_posts_pending_cost(client, pending_cost_flow):
    reopened = _ok(
        client.post(
            "/api/v1/finance/periods/reopen",
            json={"period": "2027-03", "remark": "补记暂存成本"},
            headers=pending_cost_flow["finance"],
        )
    )
    assert reopened["status"] == "OPEN"

    with SessionLocal() as db:
        pending = list(
            db.execute(
                select(PendingCost).where(
                    PendingCost.biz_type == "EXPENSE",
                    PendingCost.biz_id == pending_cost_flow["expense_id"],
                )
            )
            .scalars()
            .all()
        )
        assert pending and all(row.status == "POSTED" for row in pending)
        assert all(row.cost_record_id for row in pending)
        costs = list(
            db.execute(
                select(CostRecord).where(
                    CostRecord.biz_type == "EXPENSE",
                    CostRecord.biz_id == pending_cost_flow["expense_id"],
                )
            )
            .scalars()
            .all()
        )
        assert len(costs) == len(pending) == 1
        assert float(costs[0].amount) == 88.0
        # 再次补记不会重复入账（record_key 幂等）
        again = post_pending_costs(db, company_id=pending_cost_flow["company_id"], limit=200)
        assert again["posted"] == 0
        assert db.execute(
            select(func.count(CostRecord.id)).where(
                CostRecord.biz_type == "EXPENSE",
                CostRecord.biz_id == pending_cost_flow["expense_id"],
            )
        ).scalar_one() == 1
        db.commit()


# ------------------------------------------------------------ 3. 报销付款单唯一
def test_expense_payment_is_unique(client, pending_cost_flow):
    payload = {
        "project_id": pending_cost_flow["project_id"],
        "expense_id": pending_cost_flow["expense_id"],
        "amount": "88.00",
        "method": "BANK",
        "remark": "报销付款唯一性",
    }
    first = client.post(
        "/api/v1/finance/payments", json=payload, headers=pending_cost_flow["finance"]
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/finance/payments", json=payload, headers=pending_cost_flow["finance"]
    )
    assert second.status_code == 422, second.text
    assert "已存在付款单" in second.json()["msg"]

    with SessionLocal() as db:
        count = db.execute(
            select(func.count(Payment.id)).where(
                Payment.expense_id == pending_cost_flow["expense_id"]
            )
        ).scalar_one()
    assert count == 1


# ------------------------------------------------------------ 4. 付款重复入账与已付金额聚合
def test_pay_payment_is_idempotent(client, auth, demo):
    finance = auth("finance")
    with SessionLocal() as db:
        contract = db.execute(
            select(Contract)
            .where(Contract.project_id.is_not(None), Contract.status != "TERMINATED")
            .order_by(Contract.id)
        )
        contract = contract.scalars().first()
        assert contract is not None, "演示数据应存在已关联项目的合同"
        contract_id = contract.id
        vendor_id = contract.vendor_id
        project_id = contract.project_id

    created = _ok(
        client.post(
            "/api/v1/finance/payments",
            json={
                "project_id": project_id,
                "vendor_id": vendor_id,
                "contract_id": contract_id,
                "amount": "10.00",
                "method": "BANK",
                "remark": "重复付款幂等验证",
            },
            headers=finance,
        )
    )
    payment_id = int(created["id"])
    paid = _ok(client.post(f"/api/v1/finance/payments/{payment_id}/pay", json={}, headers=finance))
    assert paid["status"] == "PAID"

    with SessionLocal() as db:
        aggregated = Decimal(
            str(
                db.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.vendor_id == vendor_id,
                        Payment.project_id == project_id,
                        Payment.contract_id == contract_id,
                        Payment.status == "PAID",
                    )
                ).scalar_one()
            )
        )
        row = db.execute(
            select(VendorProject).where(
                VendorProject.vendor_id == vendor_id,
                VendorProject.project_id == project_id,
                VendorProject.contract_id == contract_id,
            )
        ).scalar_one_or_none()
    assert row is not None, "付款后应重算合作项目已付金额"
    assert Decimal(str(row.paid_amount)) == aggregated

    duplicated = client.post(
        f"/api/v1/finance/payments/{payment_id}/pay", json={}, headers=finance
    )
    assert duplicated.status_code == 422, duplicated.text
    assert "仅待付款状态可执行付款" in duplicated.json()["msg"]
    with SessionLocal() as db:
        refreshed = db.execute(
            select(VendorProject).where(
                VendorProject.vendor_id == vendor_id,
                VendorProject.project_id == project_id,
                VendorProject.contract_id == contract_id,
            )
        ).scalar_one()
    assert Decimal(str(refreshed.paid_amount)) == aggregated, "重复付款不得叠加已付金额"


# ------------------------------------------------------------ 5. 导出审计
def test_report_export_writes_audit(client, auth):
    finance = auth("finance")
    exported = client.get(
        "/api/v1/reports/PROFIT/export",
        params={"format": "excel", "start": "2026-11", "end": "2026-11"},
        headers=finance,
    )
    assert exported.status_code == 200, exported.text
    assert exported.content[:2] == b"PK"

    with SessionLocal() as db:
        row = db.execute(
            select(AuditLog).where(AuditLog.action == "EXPORT_REPORT").order_by(AuditLog.id.desc())
        )
        row = row.scalars().first()
    assert row is not None, "导出报表必须留下审计记录"
    assert row.after_json["code"] == "PROFIT"
    assert row.after_json["format"] == "excel"
    assert row.after_json["start"] == "2026-11"
    assert row.after_json["end"] == "2026-11"


# ------------------------------------------------------------ 6. 审批效率超时率口径
def test_approval_efficiency_overdue_rate_by_biz_type(demo):
    samples = (("TEST_EFF_A", 4, 1), ("TEST_EFF_B", 2, 2))
    with SessionLocal() as db:
        for index, (biz_type, total, overdue) in enumerate(samples):
            instance = WorkflowInstance(
                company_id=demo["company_id"],
                dept_id=None,
                project_id=None,
                creator_id=demo["users"]["pm"],
                def_id=0,
                def_code="TEST_EFF",
                biz_type=biz_type,
                biz_id=910000 + index,
                title=f"{biz_type} 效率样本",
                initiator_id=demo["users"]["pm"],
                current_node="END",
                status="APPROVED",
                context_json={},
                start_at=datetime(2026, 11, 5, 9, 0),
                finish_at=datetime(2026, 11, 5, 17, 0),
            )
            db.add(instance)
            db.flush()
            for task_index in range(total):
                is_overdue = task_index < overdue
                db.add(
                    WorkflowTask(
                        company_id=demo["company_id"],
                        instance_id=instance.id,
                        node_code="APPROVER_1",
                        node_name="审批",
                        assignee_id=demo["users"]["manager"],
                        candidate_ids=[demo["users"]["manager"]],
                        status="PENDING" if is_overdue else "DONE",
                        mode="ANY",
                        arrive_at=datetime(2026, 11, 5, 9, 0),
                        due_at=datetime(2000, 1, 1) if is_overdue else None,
                        finish_at=None if is_overdue else datetime(2026, 11, 5, 10, 0),
                    )
                )
        db.commit()

        ctx = _super_ctx(demo["company_id"])
        data = metrics_service.approval_efficiency(db, ctx, start="2026-11", end="2026-11")

    items = {item["biz_type"]: item for item in data["items"]}
    # 分母按业务类型收敛：1/4=25%，2/2=100%（若按全局任务数会统一变成 50%）
    assert items["TEST_EFF_A"]["overdue_tasks"] == 1
    assert items["TEST_EFF_A"]["overdue_rate"] == 25.0
    assert items["TEST_EFF_B"]["overdue_tasks"] == 2
    assert items["TEST_EFF_B"]["overdue_rate"] == 100.0


# ------------------------------------------------------------ 7/8. 基线口径与关闭校验
@pytest.fixture(scope="module")
def baseline_projects(demo) -> dict:
    with SessionLocal() as db:
        plan = Project(
            company_id=demo["company_id"],
            dept_id=None,
            no="PRJ-HARDEN-PLAN",
            name="A&B <一期> 基线样本",
            manager_id=demo["users"]["pm"],
            type="OTHER",
            stage="PLAN",
            status="ACTIVE",
            budget_amount=Decimal("1000.00"),
        )
        cancel = Project(
            company_id=demo["company_id"],
            dept_id=None,
            no="PRJ-HARDEN-CANCEL",
            name="已取消任务样本",
            manager_id=demo["users"]["pm"],
            type="OTHER",
            stage="EXECUTE",
            status="ACTIVE",
        )
        db.add_all([plan, cancel])
        db.flush()
        for index in range(2):
            db.add(
                Task(
                    company_id=demo["company_id"],
                    project_id=plan.id,
                    name=f"计划任务{index + 1}",
                    status="TODO",
                    estimate_hours=Decimal("5.0"),
                )
            )
            db.add(
                Task(
                    company_id=demo["company_id"],
                    project_id=cancel.id,
                    name=f"已取消任务{index + 1}",
                    status="CANCELED",
                    estimate_hours=Decimal("3.0"),
                )
            )
        db.commit()
        return {"company_id": demo["company_id"], "plan": plan.id, "cancel": cancel.id}


def test_project_deviation_uses_latest_baseline(baseline_projects, demo):
    with SessionLocal() as db:
        user = db.get(User, demo["users"]["pm"])
        ctx = _super_ctx(baseline_projects["company_id"])
        project_service.confirm_plan(db, user, ctx, baseline_projects["plan"])
        db.commit()

        project = db.get(Project, baseline_projects["plan"])
        project.stage = "PLAN"  # 模拟计划调整后的第二次确认
        db.commit()
        project_service.confirm_plan(db, user, ctx, baseline_projects["plan"])
        db.commit()

        data = project_service.project_deviation(db, ctx, baseline_projects["plan"])

    assert int(data["baseline_version"]) == 2
    assert int(data["baseline_tasks"]) == 2
    assert float(data["planned_hours"]) == 10.0, "偏差只对照最新基线，不得跨版本累加"


def test_close_check_ignores_canceled_task(baseline_projects):
    with SessionLocal() as db:
        ctx = _super_ctx(baseline_projects["company_id"])
        data = project_service.close_check(db, ctx, baseline_projects["cancel"])
    assert not any("未完成任务" in item for item in data["blockers"])


# ------------------------------------------------------------ 9. 导出转义与公式注入
def test_pdf_export_escapes_markup():
    payload = {
        "total": 1,
        "items": [{"vendor_name": "A&B <一期>", "spend": 10.0}],
        "remark": "A&B <一期>",
    }
    content = export_service.build_pdf("VENDOR_SPEND", payload)
    assert content.startswith(b"%PDF")
    assert export_service._excel_cell("=1+1") == "'=1+1"
    assert export_service._excel_cell("A&B") == "A&B"


# ------------------------------------------------------------ 10. Cookie 会话 + CSRF
def test_cookie_session_requires_csrf(client):
    logged = client.post("/api/v1/auth/login", json=_login_payload("finance"))
    assert logged.status_code == 200, logged.text
    data = logged.json()["data"]
    assert "access_token" not in data and "refresh_token" not in data
    csrf_token = data["csrf_token"]
    assert csrf_token

    denied = client.post("/api/v1/reports/snapshots/generate", params={"period": "2026-11"})
    assert denied.status_code == 403, denied.text
    assert "CSRF" in denied.json()["msg"]

    allowed = client.post(
        "/api/v1/reports/snapshots/generate",
        params={"period": "2026-11"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert allowed.status_code == 200, allowed.text

    logged_out = client.post(
        "/api/v1/auth/logout", json={}, headers={"X-CSRF-Token": csrf_token}
    )
    assert logged_out.status_code == 200


# ------------------------------------------------------------ 11. 刷新令牌重放检测
def test_refresh_replay_revokes_sessions():
    credentials = _login_payload("auditor")
    with SessionLocal() as db:
        session = auth_service.login(
            db,
            username=credentials["username"],
            password=credentials["password"],
            captcha_id=credentials["captcha_id"],
            captcha_code=credentials["captcha_code"],
            ip="127.0.0.1",
            ua="pytest",
        )
        db.commit()
        old_refresh = session["refresh_token"]
        old_payload = decode_token(old_refresh, "refresh")
        user_id = int(old_payload["sub"])
        rotated = auth_service.refresh(db, old_refresh, "127.0.0.1", "pytest")
        db.commit()
        assert rotated["refresh_token"] != old_refresh

    # 模拟并发窗口：两次刷新都通过了会话校验，第二个请求才会命中「已轮换」分支
    replay_jti = str(old_payload["jti"])
    cache.delete(f"bl:refresh:{replay_jti}")
    sessions = cache.get_json(f"sess:{user_id}") or []
    if not any(item.get("jti") == replay_jti for item in sessions):
        sessions.append(
            {
                "jti": replay_jti,
                "expire_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "ip": "127.0.0.1",
                "ua": "pytest",
            }
        )
        cache.set_json(f"sess:{user_id}", sessions, 3600)

    with SessionLocal() as db:
        with pytest.raises(UnauthorizedError):
            auth_service.refresh(db, old_refresh, "127.0.0.1", "pytest")
        db.commit()

    assert cache.get_json(f"sess:{user_id}") is None, "检测到重放后应清空该用户全部会话"
    with SessionLocal() as db:
        row = db.execute(
            select(AuditLog).where(
                AuditLog.action == "REFRESH_REPLAY_DETECTED",
                AuditLog.target_id == str(user_id),
            )
        )
        assert row.scalars().first() is not None


# ------------------------------------------------------------ 12. CC 节点
def test_cc_node_writes_copy_and_notification(demo):
    with SessionLocal() as db:
        pm = db.get(User, demo["users"]["pm"])
        finance_id = demo["users"]["finance"]
        definition = WorkflowDefinition(
            company_id=pm.company_id,
            code="TEST_CC_FLOW",
            name="抄送流程",
            version=1,
            nodes_json={
                "settings": {"due_hours": 24},
                "nodes": [
                    {"code": "START", "name": "发起人提交", "type": "START"},
                    {
                        "code": "CC_FINANCE",
                        "name": "抄送财务",
                        "type": "CC",
                        "assignee": {"type": "USER", "value": finance_id},
                    },
                    {"code": "END", "name": "归档", "type": "END"},
                ],
            },
            enabled=True,
        )
        db.add(definition)
        db.flush()
        instance = engine.start_workflow(
            db,
            company_id=pm.company_id,
            dept_id=pm.dept_id,
            project_id=None,
            initiator=pm,
            def_code="TEST_CC_FLOW",
            biz_type="TEST_CC",
            biz_id=920001,
            title="抄送节点回归",
            context={},
        )
        db.commit()
        instance_id = instance.id

    with SessionLocal() as db:
        cc = db.execute(
            select(WorkflowCc).where(
                WorkflowCc.instance_id == instance_id, WorkflowCc.user_id == finance_id
            )
        ).scalar_one_or_none()
        assert cc is not None, "CC 节点应写入 wf_cc"
        notification = db.execute(
            select(Notification).where(
                Notification.biz_type == "TEST_CC",
                Notification.biz_id == 920001,
                Notification.user_id == finance_id,
            )
        )
        notification = notification.scalars().first()
        assert notification is not None, "CC 节点应产生站内通知"
        assert notification.title.startswith("抄送")
        actions = list(
            db.execute(
                select(WorkflowRecord.action).where(WorkflowRecord.instance_id == instance_id)
            ).scalars()
        )
        assert "CC" in actions, "流程记录应留痕 CC 动作"


# ------------------------------------------------------------ 13. 变更撤回置为已取消
@pytest.fixture(scope="module")
def change_project(demo) -> dict:
    """独立项目承载变更单，避免与基线/关闭校验用例互相影响。"""
    with SessionLocal() as db:
        project = Project(
            company_id=demo["company_id"],
            dept_id=None,
            no="PRJ-HARDEN-CHANGE",
            name="变更撤回样本",
            manager_id=demo["users"]["pm"],
            type="OTHER",
            stage="EXECUTE",
            status="ACTIVE",
            budget_amount=Decimal("1000.00"),
        )
        db.add(project)
        db.commit()
        return {"id": project.id}


def test_change_withdrawn_marks_canceled(client, auth, change_project, demo):
    pm = auth("pm")
    change = _ok(
        client.post(
            f"/api/v1/projects/{change_project['id']}/changes",
            json={
                "type": "BUDGET",
                "after": {"budget_amount": "1500"},
                "reason": "撤回场景回归验证追加预算",
            },
            headers=pm,
        )
    )
    change_id = int(change["id"])
    instance_id = int(change["instance_id"])

    # 变更单没有独立撤回接口，与其余单据一样走流程引擎的 WITHDRAW 动作
    with SessionLocal() as db:
        initiator = db.get(User, demo["users"]["pm"])
        engine.act(db, user=initiator, instance_id=instance_id, action="WITHDRAW")
        db.commit()

    with SessionLocal() as db:
        row = db.get(Change, change_id)
        assert row is not None
        assert row.status == "CANCELED", "撤回后变更单应为已取消，而非悬挂在 RUNNING"
        audit = db.execute(
            select(AuditLog).where(
                AuditLog.action == "PROJECT_CHANGE_CANCELED",
                AuditLog.target_type == "PROJECT_CHANGE",
                AuditLog.target_id == str(change_id),
            )
        ).scalars().first()
        assert audit is not None, "撤回需留审计记录"