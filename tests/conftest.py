"""测试基座：独立 SQLite 库 + 内存缓存 + 本地存储，复用 seed 演示数据。

必须在导入任何 app 模块之前写入环境变量，避免 settings/engine 提前初始化。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="eoms-tests-"))

os.environ.update(
    {
        "EOMS_ENV": "test",
        "EOMS_DEBUG": "false",
        "EOMS_DATABASE_URL": f"sqlite:///{(_TMP / 'eoms.db').as_posix()}",
        "EOMS_REDIS_URL": "",
        "EOMS_STORAGE_BACKEND": "local",
        "EOMS_LOCAL_STORAGE_DIR": str(_TMP / "storage"),
        "EOMS_RLS_ENABLED": "false",
        "EOMS_CELERY_ALWAYS_EAGER": "true",
        "EOMS_SECRET_KEY": "eoms-test-secret-key-please-change",
        "EOMS_CORS_ORIGINS": "http://testserver",
        "EOMS_TRUSTED_HOSTS": "*",
        "EOMS_RATE_LIMIT_PER_MINUTE": "100000",
        "EOMS_LOGIN_RATE_LIMIT_PER_MINUTE": "100000",
    }
)

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> None:
    from scripts import seed

    seed.run(reset=True, snapshots=True)


@pytest.fixture(scope="session")
def client(seeded_database: None):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def token_for(seeded_database: None):
    from app.core.security import create_token
    from app.db.session import SessionLocal
    from app.models.iam import User

    cache: dict[str, str] = {}

    def build(username: str) -> str:
        if username in cache:
            return cache[username]
        with SessionLocal() as db:
            user = db.execute(select(User).where(User.username == username)).scalar_one()
            password_ts = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0
            token, _, _ = create_token(
                user.id,
                user.username,
                user.company_id,
                user.is_super,
                "access",
                password_ts,
            )
        cache[username] = token
        return token

    return build


@pytest.fixture(scope="session")
def auth(token_for):
    def build(username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(username)}"}

    return build


@pytest.fixture(scope="session")
def demo(seeded_database: None) -> dict:
    """返回演示数据中的关键 ID，避免测试硬编码。"""
    from app.db.session import SessionLocal
    from app.models.iam import Company, Dept, User
    from app.models.project import Project

    with SessionLocal() as db:
        company = db.execute(select(Company).where(Company.code == "DEMO")).scalar_one()
        projects = db.execute(select(Project).order_by(Project.id)).scalars().all()
        users = {
            user.username: user.id for user in db.execute(select(User)).scalars().all()
        }
        depts = {dept.code: dept.id for dept in db.execute(select(Dept)).scalars().all()}
        return {
            "company_id": company.id,
            "project_ids": [project.id for project in projects],
            "projects": {
                project.id: {"company_id": project.company_id, "dept_id": project.dept_id}
                for project in projects
            },
            "users": users,
            "depts": depts,
        }


@pytest.fixture(scope="session")
def outsider(seeded_database: None) -> dict:
    """另一个公司 + 项目 + COMPANY 数据域用户，用于越权隔离测试。"""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.iam import Company, Dept, Permission, Role, RolePermission, User
    from app.models.project import Project

    with SessionLocal() as db:
        company = Company(name="外部测试公司", code="OUTSIDE", status="ACTIVE")
        db.add(company)
        db.flush()
        dept = Dept(company_id=company.id, name="外部部门", code="OUT", path="/", sort=1)
        db.add(dept)
        db.flush()
        dept.path = f"/{dept.id}/"

        project = Project(
            company_id=company.id,
            dept_id=dept.id,
            no="PRJ-OUTSIDE-0001",
            name="外部公司项目",
            manager_id=0,
            type="OTHER",
            stage="EXECUTION",
            status="ACTIVE",
        )
        db.add(project)

        permission = db.execute(select(Permission).where(Permission.code == "project:view")).scalar_one()
        role = Role(
            company_id=company.id,
            code="OUTSIDER",
            name="外部查看者",
            data_scope="COMPANY",
            status="ACTIVE",
        )
        db.add(role)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        user = User(
            company_id=company.id,
            dept_id=dept.id,
            username="outsider",
            password_hash=hash_password("Eoms@2026", username="outsider"),
            real_name="外部用户",
            status="ACTIVE",
            first_login=False,
            role_ids=[role.id],
        )
        db.add(user)
        db.flush()
        project.manager_id = user.id
        db.commit()
        return {
            "company_id": company.id,
            "user_id": user.id,
            "project_id": project.id,
        }


@pytest.fixture(scope="session")
def admin_headers(seeded_database: None) -> dict[str, str]:
    """演示数据之外的系统管理员（不受首登改密拦截），用于 IAM 管理接口测试。"""
    from app.core.security import create_token, hash_password
    from app.db.session import SessionLocal
    from app.models.iam import Company, Dept, Role, User

    with SessionLocal() as db:
        company = db.execute(select(Company).where(Company.code == "DEMO")).scalar_one()
        dept = db.execute(select(Dept).where(Dept.company_id == company.id)).scalars().first()
        role = db.execute(select(Role).where(Role.code == "ADMIN")).scalar_one()
        user = User(
            company_id=company.id,
            dept_id=dept.id if dept else None,
            username="iamadmin",
            password_hash=hash_password("Eoms@2026", username="iamadmin"),
            real_name="测试管理员",
            status="ACTIVE",
            first_login=False,
            role_ids=[role.id],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token, _, _ = create_token(user.id, user.username, user.company_id, False, "access", 0)
    return {"Authorization": f"Bearer {token}"}
