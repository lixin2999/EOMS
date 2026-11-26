"""认证与账号安全：验证码、登录锁定、令牌轮换、登出黑名单、首登改密。"""

from __future__ import annotations

from app.core.cache import cache
from app.core.security import check_password_strength, create_token, hash_password, verify_password
from app.services.iam import auth as auth_service

DEMO_PASSWORD = "Eoms@2026"
_INVALID_CREDENTIALS_MESSAGE = "用户名或者密码错误，请重新输入或者联系管理员"


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
    # 令牌只写 HttpOnly Cookie，响应体不返回明文
    assert "access_token" not in data and "refresh_token" not in data
    assert data["csrf_token"]
    assert data["user"]["username"] == "director"
    assert "project:view" in data["user"]["permissions"]
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("eoms_at=") and "HttpOnly" in cookie for cookie in cookies)
    assert any(cookie.startswith("eoms_rt=") and "HttpOnly" in cookie for cookie in cookies)
    assert any(cookie.startswith("eoms_csrf=") and "HttpOnly" not in cookie for cookie in cookies)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    profile = me.json()["data"]
    assert profile["company_name"]
    assert profile["menus"], "登录用户应返回可见菜单树"
    assert client.post(
        "/api/v1/auth/logout", json={}, headers={"X-CSRF-Token": data["csrf_token"]}
    ).status_code == 200


def test_login_with_idempotency_key_preserves_session_cookies(client):
    client.cookies.clear()
    headers = {"Idempotency-Key": "auth-login-regression"}
    first = client.post("/api/v1/auth/login", json=_login_payload("pm"), headers=headers)
    assert first.status_code == 200, first.text
    first_cookies = first.headers.get_list("set-cookie")
    assert {cookie.split("=", 1)[0] for cookie in first_cookies} == {"eoms_at", "eoms_rt", "eoms_csrf"}
    assert client.get("/api/v1/auth/me").status_code == 200

    # 认证请求不参与业务幂等，即使携带相同键也不能回放首次登录响应。
    second = client.post("/api/v1/auth/login", json=_login_payload("pm"), headers=headers)
    assert second.status_code == 200, second.text
    assert len(second.headers.get_list("set-cookie")) == 3
    assert second.json()["data"]["csrf_token"] != first.json()["data"]["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200


def test_refresh_and_logout_ignore_idempotency_header(client):
    client.cookies.clear()
    logged = client.post("/api/v1/auth/login", json=_login_payload("finance"))
    assert logged.status_code == 200, logged.text

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={},
        headers={"Idempotency-Key": "auth-refresh-regression"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert {cookie.split("=", 1)[0] for cookie in refreshed.headers.get_list("set-cookie")} == {
        "eoms_at",
        "eoms_rt",
        "eoms_csrf",
    }
    assert client.get("/api/v1/auth/me").status_code == 200

    logged_out = client.post(
        "/api/v1/auth/logout",
        json={},
        headers={
            "Idempotency-Key": "auth-logout-regression",
            "X-CSRF-Token": refreshed.json()["data"]["csrf_token"],
        },
    )
    assert logged_out.status_code == 200, logged_out.text
    cleared = logged_out.headers.get_list("set-cookie")
    for name in ("eoms_at", "eoms_rt", "eoms_csrf"):
        assert any(cookie.startswith(f"{name}=") and "Max-Age=0" in cookie for cookie in cleared)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_idempotency_rebuild_preserves_all_set_cookie_headers(client, auth, monkeypatch):
    from app.main import IDEMPOTENCY_EXEMPT

    # 单独验证通用响应重建：临时让登录经过幂等中间件，确认同名头不会被覆盖。
    monkeypatch.setattr("app.main.IDEMPOTENCY_EXEMPT", IDEMPOTENCY_EXEMPT - {"/api/v1/auth/login"})
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json=_login_payload("pm"),
        # 携带有效 Bearer Token，确保中间件进入 _forward，而不是因无令牌提前跳过。
        headers={**auth("pm"), "Idempotency-Key": "cookie-header-rebuild-regression"},
    )
    assert response.status_code == 200, response.text
    assert len(response.headers.get_list("set-cookie")) == 3
    assert client.get("/api/v1/auth/me").status_code == 200


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
        assert response.json()["code"] == 1001
        assert response.json()["msg"] == _INVALID_CREDENTIALS_MESSAGE
        assert not response.headers.get_list("set-cookie")

    locked = client.post("/api/v1/auth/login", json=_login_payload(username))
    assert locked.status_code == 423
    assert locked.json()["code"] == 1009
    cache.delete(f"login:fail:{username}")


def test_login_unknown_user_returns_credential_error(client):
    username = "no-such-eoms-user"
    cache.delete(f"login:fail:{username}")
    response = client.post("/api/v1/auth/login", json=_login_payload(username, DEMO_PASSWORD))
    assert response.status_code == 401
    assert response.json()["code"] == 1001
    assert response.json()["msg"] == _INVALID_CREDENTIALS_MESSAGE
    assert not response.headers.get_list("set-cookie")
    cache.delete(f"login:fail:{username}")


def test_refresh_token_rotates(client):
    client.post("/api/v1/auth/login", json=_login_payload("pm"))
    refreshed = client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200, refreshed.text
    data = refreshed.json()["data"]
    assert data["csrf_token"]
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "pm"
    assert client.post(
        "/api/v1/auth/logout", json={}, headers={"X-CSRF-Token": data["csrf_token"]}
    ).status_code == 200


def test_refresh_accepts_empty_body_from_cookie(client):
    client.post("/api/v1/auth/login", json=_login_payload("pm"))
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["data"]["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200


def test_logout_accepts_empty_body_and_clears_cookies(client):
    logged = client.post("/api/v1/auth/login", json=_login_payload("finance"))
    assert logged.status_code == 200, logged.text
    csrf_token = logged.json()["data"]["csrf_token"]

    logged_out = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logged_out.status_code == 200, logged_out.text
    cookies = logged_out.headers.get_list("set-cookie")
    for name in ("eoms_at", "eoms_rt", "eoms_csrf"):
        assert any(cookie.startswith(f"{name}=") and "Max-Age=0" in cookie for cookie in cookies)
    assert client.get("/api/v1/auth/me").status_code == 401


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
