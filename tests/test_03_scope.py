"""数据域隔离：公司边界、SELF/DEPT 收敛与跨公司越权访问。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.security import create_token
from app.db.session import SessionLocal
from app.models.iam import User


def _project_list(client, headers, **params):
    response = client.get("/api/v1/projects", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _token_for_outsider(user_id: int) -> str:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one()
        password_ts = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0
        token, _, _ = create_token(user.id, user.username, user.company_id, user.is_super, "access", password_ts)
        return token


def test_director_sees_whole_company(client, auth, demo):
    data = _project_list(client, auth("director"), page=1, page_size=50)
    assert data["total"] == 4
    ids = {item["id"] for item in data["items"]}
    assert ids == set(demo["project_ids"])


def test_employee_without_project_permission_gets_403(client, auth):
    response = client.get("/api/v1/projects", params={"page": 1, "page_size": 50}, headers=auth("employee"))
    assert response.status_code == 403
    assert response.json()["code"] == 1003


def test_employee_self_scope_only_sees_own_expenses(client, auth, demo):
    headers = auth("employee")
    data = client.get(
        "/api/v1/approvals/expenses",
        params={"page": 1, "page_size": 100},
        headers=headers,
    ).json()["data"]
    employee_id = demo["users"]["employee"]
    assert data["items"], "演示数据应包含员工本人报销"
    for item in data["items"]:
        assert item["applicant_id"] == employee_id, "SELF 数据域只能看到本人报销"

    director = client.get(
        "/api/v1/approvals/expenses",
        params={"page": 1, "page_size": 100},
        headers=auth("director"),
    ).json()["data"]
    assert director["total"] >= data["total"]


def test_dept_leader_only_own_department(client, auth, demo):
    data = _project_list(client, auth("leader"), page=1, page_size=50)
    leader_id = demo["users"]["leader"]
    with SessionLocal() as db:
        leader = db.get(User, leader_id)
        leader_dept = leader.dept_id
    for item in data["items"]:
        assert item["dept_id"] == leader_dept, "DEPT 数据域只能看到本部门项目"
    assert data["total"] <= 4


def test_outsider_company_isolation(client, outsider):
    headers = {"Authorization": f"Bearer {_token_for_outsider(outsider['user_id'])}"}

    own = _project_list(client, headers, page=1, page_size=50)
    assert own["total"] == 1
    assert own["items"][0]["id"] == outsider["project_id"]

    forbidden = client.get(f"/api/v1/projects/{outsider['project_id']}", headers=headers)
    assert forbidden.status_code == 200
    assert forbidden.json()["data"]["company_id"] == outsider["company_id"]


def test_cross_company_project_not_visible_to_demo_company(client, auth, outsider):
    response = client.get(f"/api/v1/projects/{outsider['project_id']}", headers=auth("director"))
    assert response.status_code == 404
    assert response.json()["code"] == 1004


def test_cross_company_outsider_cannot_read_demo_project(client, auth, demo, outsider):
    headers = {"Authorization": f"Bearer {_token_for_outsider(outsider['user_id'])}"}
    demo_project = sorted(demo["project_ids"])[0]
    response = client.get(f"/api/v1/projects/{demo_project}", headers=headers)
    assert response.status_code == 404
