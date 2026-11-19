"""认证与账号安全：验证码、登录锁定、令牌轮换、登出黑名单、首登改密。"""

from __future__ import annotations

from app.core.cache import cache
from app.core.security import check_password_strength, create_token, hash_password, verify_password
from app.services.iam import auth as auth_service

DEMO_PASSWORD = "Eoms@2026"


def _captcha() -> tuple[str, str]:
    data = auth_service.create_captcha()
    captcha_id = data["captcha_id"]
    return captcha_id, cache.get(f"captcha:{captcha_id}") or ""


def _login_payload(username: str, password: str = DEMO_PASSWORD) -> dict:
    captcha_id, code = _captcha()
    return {
        "username": username,
        "password": password,
        "captcha_id": captcha_id,
        "captcha_code": code,
    }


def test_captcha_endpoint(client):
    response = client.get("/api/v1/auth/captcha")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["image"].startswith("data:image/png;base64,")
    assert data["expires_in"] > 0
    assert cache.get(f"captcha:{data['captcha_id']}")


def test_login_and_profile(client):
    response = client.post("/api/v1/auth/login", json=_login_payload("director"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["user"]["username"] == "director"
    assert "project:view" in data["user"]["permissions"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    profile = me.json()["data"]
    assert profile["company_name"]
    assert profile["menus"], "登录用户应返回可见菜单树"


def test_login_rejects_invalid_captcha(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "director",
            "password": DEMO_PASSWORD,
            "captcha_id": "not-exists",
            "captcha_code": "xxxx",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == 1010


def test_login_wrong_password_and_lock(client):
    username = "purchase"
    cache.delete(f"login:fail:{username}")
    for _ in range(5):
        response = client.post("/api/v1/auth/login", json=_login_payload(username, "WrongPass1"))
        assert response.status_code == 401

    locked = client.post("/api/v1/auth/login", json=_login_payload(username))
    assert locked.status_code == 423
    assert locked.json()["code"] == 1009
    cache.delete(f"login:fail:{username}")


def test_refresh_token_rotates(client):
    login = client.post("/api/v1/auth/login", json=_login_payload("pm")).json()["data"]
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()["data"]["access_token"]
    assert new_access != login["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


def test_logout_blacklists_access_token(client, token_for):
    token = token_for("auditor")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_admin_first_login_must_change_password(client, auth):
    headers = auth("admin")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["first_login"] is True

    blocked = client.get("/api/v1/projects", headers=headers)
    assert blocked.status_code == 403
    assert "首次登录" in blocked.json()["msg"]

    wrong_old = client.put(
        "/api/v1/auth/password",
        json={"old_password": "NotTheOld1", "new_password": "Another@2026"},
        headers=headers,
    )
    assert wrong_old.status_code == 422, wrong_old.text
    assert wrong_old.json()["code"] == 3000


def test_tampered_token_rejected(client):
    token, _, _ = create_token(1, "admin", 1, True, "access", 0)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}x"})
    assert response.status_code == 401
    assert response.json()["code"] in {1001, 1002}


def test_password_strength_and_hash():
    assert check_password_strength("Eoms@2026", username="someone") == []
    assert check_password_strength("abc12345", username="someone") != []
    errors = check_password_strength("12345678", username="someone")
    assert errors
    hashed = hash_password("Eoms@2026", username="someone")
    assert verify_password("Eoms@2026", hashed, username="someone")
    assert not verify_password("Eoms@2027", hashed, username="someone")
