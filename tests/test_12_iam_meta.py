"""平台管理：用户、角色、部门、字典、参数、客户与审计日志。"""

from __future__ import annotations

import uuid

import pytest


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


@pytest.fixture(scope="module")
def roles(client, admin_headers):
    data = _ok(client.get("/api/v1/iam/roles", headers=admin_headers))
    mapping = {item["code"]: item for item in data}
    assert {"ADMIN", "DIRECTOR", "EMPLOYEE"} <= set(mapping)
    return mapping


def test_permission_tree(client, admin_headers):
    tree = _ok(client.get("/api/v1/iam/permissions/tree", headers=admin_headers))
    assert tree
    flat: list[dict] = []

    def walk(nodes):
        for node in nodes:
            flat.append(node)
            walk(node.get("children") or [])

    walk(tree)
    assert any(item.get("code") == "system:user" for item in flat)


@pytest.fixture(scope="module")
def dept(client, admin_headers):
    suffix = uuid.uuid4().hex[:6]
    root = _ok(client.get("/api/v1/iam/depts/tree", headers=admin_headers))
    assert root
    created = _ok(
        client.post(
            "/api/v1/iam/depts",
            json={"name": f"测试部门-{suffix}", "code": f"T{suffix.upper()}", "parent_id": root[0]["id"], "sort": 99},
            headers=admin_headers,
        )
    )
    child = _ok(
        client.post(
            "/api/v1/iam/depts",
            json={"name": f"测试子部门-{suffix}", "parent_id": created["id"], "sort": 1},
            headers=admin_headers,
        )
    )
    return {"id": created["id"], "child_id": child["id"], "root_id": root[0]["id"]}


def test_dept_tree_and_update(client, admin_headers, dept):
    tree = _ok(client.get("/api/v1/iam/depts/tree", headers=admin_headers))
    ids = {item["id"] for item in tree}
    assert dept["root_id"] in ids

    updated = _ok(
        client.put(
            f"/api/v1/iam/depts/{dept['id']}",
            json={"name": "测试部门（改名）", "parent_id": dept["root_id"], "sort": 5},
            headers=admin_headers,
        )
    )
    assert updated["name"] == "测试部门（改名）"

    cycle = client.put(
        f"/api/v1/iam/depts/{dept['id']}",
        json={"name": "循环移动", "parent_id": dept["child_id"]},
        headers=admin_headers,
    )
    assert cycle.status_code == 422
    assert cycle.json()["code"] == 3000


@pytest.fixture(scope="module")
def new_role(client, admin_headers, roles):
    suffix = uuid.uuid4().hex[:6]
    employee = roles["EMPLOYEE"]
    created = _ok(
        client.post(
            "/api/v1/iam/roles",
            json={
                "code": f"TEST{suffix.upper()}",
                "name": f"测试角色-{suffix}",
                "data_scope": "SELF",
                "permission_ids": employee["permission_ids"][:2],
                "remark": "自动化测试角色",
            },
            headers=admin_headers,
        )
    )
    return {"id": created["id"], "code": created["code"], "permission_ids": employee["permission_ids"][:2]}


def test_role_create_update_delete(client, admin_headers, new_role):
    listed = _ok(client.get("/api/v1/iam/roles", headers=admin_headers))
    row = next(item for item in listed if item["id"] == new_role["id"])
    assert row["data_scope"] == "SELF"
    assert row["permission_ids"]

    updated = _ok(
        client.put(
            f"/api/v1/iam/roles/{new_role['id']}",
            json={
                "code": new_role["code"],
                "name": "测试角色（更新）",
                "data_scope": "COMPANY",
                "permission_ids": new_role["permission_ids"],
            },
            headers=admin_headers,
        )
    )
    assert updated["data_scope"] == "COMPANY"

    duplicate = client.post(
        "/api/v1/iam/roles",
        json={"code": new_role["code"], "name": "重复角色", "data_scope": "SELF"},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409

    builtin = client.delete(f"/api/v1/iam/roles/{new_role['id']}", headers=admin_headers)
    assert builtin.status_code == 200


def test_builtin_role_cannot_be_deleted(client, admin_headers, roles):
    response = client.delete(f"/api/v1/iam/roles/{roles['DIRECTOR']['id']}", headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["code"] == 3000


@pytest.fixture(scope="module")
def user(client, admin_headers, dept):
    suffix = uuid.uuid4().hex[:6]
    # 新角色已删除，改用员工角色创建用户
    roles = _ok(client.get("/api/v1/iam/roles", headers=admin_headers))
    employee = next(item for item in roles if item["code"] == "EMPLOYEE")
    created = _ok(
        client.post(
            "/api/v1/iam/users",
            json={
                "username": f"tester{suffix}",
                "real_name": f"测试用户-{suffix}",
                "password": "Eoms@2026",
                "dept_id": dept["id"],
                "position": "测试工程师",
                "phone": "13800009999",
                "email": f"tester{suffix}@demo-eoms.cn",
                "role_ids": [employee["id"]],
                "first_login": True,
            },
            headers=admin_headers,
        )
    )
    return {"id": created["id"], "username": created["username"], "data": created}


def test_user_create_detail_update(client, admin_headers, user):
    detail = _ok(client.get(f"/api/v1/iam/users/{user['id']}", headers=admin_headers))
    assert detail["username"] == user["username"]
    assert detail["phone"] and "*" in detail["phone"]

    users = _ok(
        client.get(
            "/api/v1/iam/users",
            params={"page": 1, "page_size": 20, "keyword": user["username"]},
            headers=admin_headers,
        )
    )
    assert users["total"] == 1

    updated = _ok(
        client.put(
            f"/api/v1/iam/users/{user['id']}",
            json={
                "real_name": "测试用户（改名）",
                "position": "高级测试工程师",
                "version": user["data"]["version"],
            },
            headers=admin_headers,
        )
    )
    assert updated["real_name"] == "测试用户（改名）"

    conflict = client.put(
        f"/api/v1/iam/users/{user['id']}",
        json={"real_name": "过期版本", "version": user["data"]["version"]},
        headers=admin_headers,
    )
    assert conflict.status_code == 409


def test_user_duplicate_and_bad_password(client, admin_headers, user):
    duplicate = client.post(
        "/api/v1/iam/users",
        json={
            "username": user["username"],
            "real_name": "重复用户",
            "password": "Eoms@2026",
        },
        headers=admin_headers,
    )
    assert duplicate.status_code == 409

    weak = client.post(
        "/api/v1/iam/users",
        json={
            "username": f"weak{uuid.uuid4().hex[:6]}",
            "real_name": "弱密码用户",
            "password": "12345678",
        },
        headers=admin_headers,
    )
    assert weak.status_code == 422
    assert weak.json()["code"] == 3000


def test_reset_password_and_disable_user(client, admin_headers, user):
    _ok(
        client.post(
            f"/api/v1/iam/users/{user['id']}/reset-password",
            json={"new_password": "Eoms@2026"},
            headers=admin_headers,
        )
    )
    disabled = _ok(
        client.put(
            f"/api/v1/iam/users/{user['id']}",
            json={"status": "DISABLED"},
            headers=admin_headers,
        )
    )
    assert disabled["status"] == "DISABLED"
    _ok(
        client.put(
            f"/api/v1/iam/users/{user['id']}",
            json={"status": "ACTIVE"},
            headers=admin_headers,
        )
    )


def test_audit_logs(client, admin_headers, user):
    result = _ok(
        client.get(
            "/api/v1/iam/audit-logs",
            params={"page": 1, "page_size": 50, "target_type": "USER"},
            headers=admin_headers,
        )
    )
    assert result["items"]
    assert result["total"] >= 1

    actions = _ok(
        client.get(
            "/api/v1/iam/audit-logs",
            params={"page": 1, "page_size": 20, "action": "CREATE_USER"},
            headers=admin_headers,
        )
    )
    assert actions["items"]


def test_dict_crud(client, admin_headers):
    suffix = uuid.uuid4().hex[:6]
    created = _ok(
        client.post(
            "/api/v1/iam/dicts",
            json={
                "dict_type": f"test_type_{suffix}",
                "label": "测试标签",
                "value": "TEST",
                "sort": 1,
                "remark": "自动化测试",
            },
            headers=admin_headers,
        )
    )
    listed = _ok(
        client.get(
            "/api/v1/iam/dicts", params={"dict_type": f"test_type_{suffix}"}, headers=admin_headers
        )
    )
    assert any(item["id"] == created["id"] for item in listed)

    updated = _ok(
        client.put(
            f"/api/v1/iam/dicts/{created['id']}",
            json={
                "dict_type": f"test_type_{suffix}",
                "label": "测试标签（改）",
                "value": "TEST2",
            },
            headers=admin_headers,
        )
    )
    assert updated["label"] == "测试标签（改）"
    _ok(client.delete(f"/api/v1/iam/dicts/{created['id']}", headers=admin_headers))


def test_config_set_and_list(client, admin_headers):
    key = f"test.config.{uuid.uuid4().hex[:6]}"
    saved = _ok(
        client.put(
            f"/api/v1/iam/configs/{key}",
            json={"value": {"enabled": True, "limit": 10}, "description": "自动化测试参数"},
            headers=admin_headers,
        )
    )
    assert saved["key"] == key
    configs = _ok(client.get("/api/v1/iam/configs", headers=admin_headers))
    row = next(item for item in configs if item["key"] == key)
    assert row["value"]["enabled"] is True


def test_customer_crud(client, admin_headers):
    suffix = uuid.uuid4().hex[:6]
    created = _ok(
        client.post(
            "/api/v1/iam/customers",
            json={
                "name": f"测试客户-{suffix}",
                "code": f"C{suffix.upper()}",
                "contact": "王先生",
                "phone": "13900001111",
                "email": "customer@example.com",
                "address": "上海市测试路 1 号",
            },
            headers=admin_headers,
        )
    )
    assert created["phone"].startswith(("139", "****", "*"))

    listed = _ok(
        client.get("/api/v1/iam/customers", params={"keyword": suffix}, headers=admin_headers)
    )
    assert listed and listed[0]["id"] == created["id"]

    updated = _ok(
        client.put(
            f"/api/v1/iam/customers/{created['id']}",
            json={"name": f"测试客户-{suffix}-改", "code": f"C{suffix.upper()}"},
            headers=admin_headers,
        )
    )
    assert updated["name"].endswith("改")

    duplicate = client.post(
        "/api/v1/iam/customers",
        json={"name": f"测试客户-{suffix}-改", "code": f"C{suffix.upper()}"},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409
