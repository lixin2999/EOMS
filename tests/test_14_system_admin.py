"""系统管理回归：部门删除约束、菜单可见性与账号启停/改密。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.cache import cache
from app.core.errors import AppError, UnauthorizedError
from app.db.session import SessionLocal
from app.models.iam import AuditLog, Dept, User
from app.services.iam import auth as auth_service

API = "/api/v1"


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _login_payload(username: str, password: str) -> dict:
    data = auth_service.create_captcha()
    captcha_id = data["captcha_id"]
    return {
        "username": username,
        "password": password,
        "captcha_id": captcha_id,
        "captcha_code": cache.get(f"captcha:{captcha_id}") or "",
    }


def _service_login(username: str, password: str) -> dict:
    with SessionLocal() as db:
        return auth_service.login(db, **_login_payload(username, password), ip="127.0.0.1", ua="pytest")


def _create_dept(client, headers, name: str, parent_id: int | None = None) -> dict:
    return _ok(
        client.post(
            f"{API}/iam/depts",
            json={"name": name, "parent_id": parent_id},
            headers=headers,
        )
    )


def test_dept_delete_guards_children_and_writes_audit(client, admin_headers):
    parent = _create_dept(client, admin_headers, "回归-父部门")
    child = _create_dept(client, admin_headers, "回归-子部门", parent["id"])

    blocked = client.delete(f"{API}/iam/depts/{parent['id']}", headers=admin_headers)
    assert blocked.status_code == 422, blocked.text
    assert "子部门" in blocked.json()["msg"]

    _ok(client.delete(f"{API}/iam/depts/{child['id']}", headers=admin_headers))
    _ok(client.delete(f"{API}/iam/depts/{parent['id']}", headers=admin_headers))

    with SessionLocal() as db:
        assert db.get(Dept, parent["id"]) is None
        audit = (
            db.execute(
                select(AuditLog).where(
                    AuditLog.action == "DELETE_DEPT",
                    AuditLog.target_id == str(parent["id"]),
                )
            )
            .scalars()
            .first()
        )
        assert audit is not None, "删除部门需留审计记录"


def test_dept_delete_blocked_when_members(client, admin_headers):
    dept = _create_dept(client, admin_headers, "回归-成员部门")
    member = _ok(
        client.post(
            f"{API}/iam/users",
            json={
                "username": "dept_member_u",
                "real_name": "部门成员",
                "password": "Aa1@abcd",
                "dept_id": dept["id"],
            },
            headers=admin_headers,
        )
    )

    denied = client.delete(f"{API}/iam/depts/{dept['id']}", headers=admin_headers)
    assert denied.status_code == 422, denied.text
    assert "用户" in denied.json()["msg"]

    # 先迁移成员归属，再删除才允许
    latest = _ok(client.get(f"{API}/iam/users/{member['id']}", headers=admin_headers))
    _ok(
        client.put(
            f"{API}/iam/users/{member['id']}",
            json={"dept_id": None, "version": latest["version"]},
            headers=admin_headers,
        )
    )
    _ok(client.delete(f"{API}/iam/depts/{dept['id']}", headers=admin_headers))
    with SessionLocal() as db:
        db.delete(db.get(User, member["id"]))
        db.commit()


def test_system_password_menu_visible_for_admin(client, admin_headers):
    profile = _ok(client.get(f"{API}/auth/me", headers=admin_headers))
    assert "system:password" in profile["permissions"], "系统管理员应获得修改密码菜单权限"

    system = next((item for item in profile["menus"] if item["code"] == "menu:system"), None)
    assert system is not None, "系统管理分组应出现在菜单树中"
    child = next((item for item in system["children"] if item["code"] == "system:password"), None)
    assert child is not None, "系统管理下应包含修改密码菜单"
    assert child["path"] == "/system/password"


def test_user_status_toggle_and_password_rotation(client, admin_headers):
    created = _ok(
        client.post(
            f"{API}/iam/users",
            json={"username": "toggle_u", "real_name": "启停回归", "password": "Aa1@abcd"},
            headers=admin_headers,
        )
    )
    user_id = int(created["id"])

    disabled = _ok(
        client.put(
            f"{API}/iam/users/{user_id}",
            json={"status": "DISABLED", "version": created["version"]},
            headers=admin_headers,
        )
    )
    with pytest.raises(AppError) as blocked:
        _service_login("toggle_u", "Aa1@abcd")
    assert "停用" in str(blocked.value)

    enabled = _ok(
        client.put(
            f"{API}/iam/users/{user_id}",
            json={"status": "ACTIVE", "version": disabled["version"]},
            headers=admin_headers,
        )
    )
    assert enabled["status"] == "ACTIVE"
    assert _service_login("toggle_u", "Aa1@abcd")["user"]["username"] == "toggle_u"

    with SessionLocal() as db:
        user = db.get(User, user_id)
        auth_service.change_password(db, user, "Aa1@abcd", "Bb2@efgh")
        db.commit()
        assert user.first_login is False

    with pytest.raises(UnauthorizedError):
        _service_login("toggle_u", "Aa1@abcd")
    assert _service_login("toggle_u", "Bb2@efgh")["user"]["username"] == "toggle_u"

    with SessionLocal() as db:
        db.delete(db.get(User, user_id))
        db.commit()
