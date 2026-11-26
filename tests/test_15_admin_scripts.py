"""演示数据清理与超级管理员初始化脚本回归测试。"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.errors import BusinessRuleError
from app.core.security import hash_password, verify_password
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.approval import ExpenseItem
from app.models.iam import AuditLog, Company, Dept, Permission, Role, RolePermission, SysConfig, SysFile, User
from app.models.platform import Sequence
from app.models.project import Project, TaskBaseline
from scripts import seed
from scripts.clear_demo import CleanupResult, _clear_runtime_state, _tenant_tables, clear_demo_data
from scripts.create_super_admin import ensure_super_admin


def test_clear_demo_dry_run_and_execute_preserves_other_data(demo, outsider):
    with SessionLocal() as db:
        company_id = demo["company_id"]
        project_id = demo["project_ids"][0]
        existing_paths = set(
            db.execute(select(SysFile.path).where(SysFile.company_id == company_id)).scalars()
        )
        permission = db.execute(select(Permission).where(Permission.code == "project:view")).scalar_one()
        tenant_role = Role(company_id=company_id, code="DEMO_CLEANUP_ROLE", name="演示清理角色", data_scope="SELF")
        db.add(tenant_role)
        db.flush()
        db.add(RolePermission(role_id=tenant_role.id, permission_id=permission.id))
        db.add(TaskBaseline(project_id=project_id, name="待清理基线", baseline_version=1))
        db.add(AuditLog(company_id=company_id, action="DEMO_CLEANUP_TEST"))
        db.add(
            SysFile(
                company_id=company_id,
                name="演示附件.txt",
                path=f"{company_id}/202611/demo-only.txt",
                size=10,
            )
        )
        shared_path = f"{company_id}/202611/shared.txt"
        db.add(SysFile(company_id=company_id, name="演示共享附件.txt", path=shared_path, size=10))
        db.add(SysFile(company_id=outsider["company_id"], name="外部共享附件.txt", path=shared_path, size=10))
        demo_sequence = db.execute(select(Sequence).where(Sequence.name == "PRJ:2026:DEMO")).scalar_one_or_none()
        if demo_sequence is None:
            db.add(Sequence(name="PRJ:2026:DEMO", current=99))
        else:
            demo_sequence.current = 99
        db.add(Sequence(name="PRJ:2026:OUTSIDE", current=7))
        db.flush()

        permission_count = db.execute(select(func.count()).select_from(Permission)).scalar_one()
        config_count = db.execute(select(func.count()).select_from(SysConfig)).scalar_one()
        admin_role = db.execute(select(Role).where(Role.code == "ADMIN")).scalar_one()
        admin_permission_count = db.execute(
            select(func.count()).select_from(RolePermission).where(RolePermission.role_id == admin_role.id)
        ).scalar_one()

        preview = clear_demo_data(db)
        assert preview is not None
        assert preview.company_id == company_id
        assert preview.counts["sys_company"] == 1
        assert preview.counts["pm_project"] >= 1
        assert preview.counts["biz_expense_item"] >= 1
        assert preview.counts["pm_task_baseline"] >= 1
        assert preview.counts["sys_role_permission"] >= 1
        assert set(preview.file_keys) == (existing_paths | {f"{company_id}/202611/demo-only.txt"}) - {shared_path}
        assert shared_path in preview.shared_file_keys
        assert db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none() is not None

        result = clear_demo_data(db, execute=True)
        assert result is not None
        assert db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none() is None
        for table in _tenant_tables():
            count = db.execute(
                select(func.count()).select_from(table).where(table.c.company_id == company_id)
            ).scalar_one()
            assert count == 0, table.name
        assert db.execute(select(func.count()).select_from(ExpenseItem)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(TaskBaseline)).scalar_one() == 0
        demo_audit_count = db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.company_id == company_id)
        ).scalar_one()
        assert demo_audit_count == 0
        assert db.execute(select(Sequence).where(Sequence.name == "PRJ:2026:DEMO")).scalar_one_or_none() is None
        assert db.execute(select(Sequence).where(Sequence.name == "PRJ:2026:OUTSIDE")).scalar_one_or_none() is not None

        assert db.execute(select(func.count()).select_from(Permission)).scalar_one() == permission_count
        assert db.execute(select(func.count()).select_from(SysConfig)).scalar_one() == config_count
        assert db.execute(select(Role).where(Role.code == "ADMIN")).scalar_one().id == admin_role.id
        assert db.execute(
            select(func.count()).select_from(RolePermission).where(RolePermission.role_id == admin_role.id)
        ).scalar_one() == admin_permission_count
        assert db.execute(select(Company).where(Company.id == outsider["company_id"])).scalar_one_or_none() is not None
        assert db.execute(select(Project).where(Project.id == outsider["project_id"])).scalar_one_or_none() is not None
        assert db.execute(select(User).where(User.id == outsider["user_id"])).scalar_one_or_none() is not None
        assert db.execute(select(SysFile).where(SysFile.path == shared_path)).scalar_one_or_none() is not None
        assert clear_demo_data(db, execute=True) is None
        db.rollback()


def test_clear_demo_runtime_state_only_removes_demo_keys():
    result = CleanupResult(company_id=10, user_ids=[20], usernames=["DemoUser"])
    keys = {
        "perm:20": "1",
        "sess:20": "1",
        "lock:sess:20": "1",
        "login:fail:demouser": "1",
        "idem:10:20:POST:/api/v1/test:key": "1",
        "idem-lock:idem:10:20:POST:/api/v1/test:key": "1",
    }
    for key, value in keys.items():
        cache.set(key, value)
    cache.set("perm:999", "keep")

    _clear_runtime_state(result)

    for key in keys:
        assert cache.get(key) is None
    assert cache.get("perm:999") == "keep"
    cache.delete("perm:999")


def test_clear_demo_requires_migrated_schema():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as db:
        try:
            clear_demo_data(db)
        except BusinessRuleError as exc:
            assert "alembic upgrade head" in str(exc)
        else:
            raise AssertionError("缺少数据表时应给出迁移提示")
    engine.dispose()


def test_create_super_admin_bootstraps_empty_schema_and_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = ensure_super_admin(
            db,
            company_code="eoms",
            company_name="示例运营公司",
            username="Admin",
            password="Strong@2026",
            real_name="系统管理员",
            email="admin@example.com",
        )
        assert first.company_created and first.department_created and first.user_created
        user = db.get(User, first.user_id)
        assert user is not None
        assert user.username == "admin"
        assert user.company_id == first.company_id
        assert user.is_super is True
        assert user.status == "ACTIVE"
        assert user.first_login is False
        assert user.password_updated_at is not None
        assert verify_password("Strong@2026", user.password_hash, username="admin")
        department = db.get(Dept, user.dept_id)
        assert department is not None and department.code == "HQ" and department.path == f"/{department.id}/"
        roles = db.execute(select(Role).where(Role.is_builtin.is_(True))).scalars().all()
        assert {role.code for role in roles} == {item[0] for item in seed.ROLE_SPECS}
        permissions = db.execute(select(func.count()).select_from(Permission)).scalar_one()
        assert permissions == len(seed.MENUS) + len(seed.APIS)
        admin_role = next(role for role in roles if role.code == "ADMIN")
        assert admin_role.id in user.role_ids
        assert db.execute(
            select(func.count()).select_from(RolePermission).where(RolePermission.role_id == admin_role.id)
        ).scalar_one() == permissions
        assert db.execute(select(func.count()).select_from(RolePermission)).scalar_one() > permissions
        assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == 1

        original_hash = user.password_hash
        original_version = user.version
        second = ensure_super_admin(
            db,
            company_code="EOMS",
            company_name="忽略重复公司名",
            username="admin",
            password="Ignored@2026",
        )
        assert not second.company_created and not second.department_created
        assert not second.user_created and not second.user_updated and not second.password_reset
        assert user.password_hash == original_hash and user.version == original_version
        assert db.execute(select(func.count()).select_from(User)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == 1

        reset = ensure_super_admin(
            db,
            company_code="EOMS",
            username="ADMIN",
            password="Replacement@2027",
            reset_password=True,
        )
        assert reset.password_reset and reset.user_updated is False
        assert verify_password("Replacement@2027", user.password_hash, username="admin")
        assert not verify_password("Strong@2026", user.password_hash, username="admin")
        assert user.version == original_version + 1
        assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == 2
    engine.dispose()


def test_create_super_admin_promotes_existing_user_without_changing_password():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(name="已有公司", code="EXISTING", status="ACTIVE")
        db.add(company)
        db.flush()
        department = Dept(company_id=company.id, name="总部", code="HQ", path="/")
        db.add(department)
        db.flush()
        original_hash = hash_password("Original@2026", username="operator")
        user = User(
            company_id=company.id,
            dept_id=department.id,
            username="operator",
            password_hash=original_hash,
            real_name="现有账号",
            role_ids=[],
            status="DISABLED",
            is_super=False,
            first_login=True,
        )
        db.add(user)
        db.flush()

        result = ensure_super_admin(db, company_code="EXISTING", username="operator")
        assert result.user_updated and not result.password_reset and not result.user_created
        assert user.is_super is True and user.status == "ACTIVE" and user.first_login is False
        assert user.password_hash == original_hash and user.role_ids
        assert user.version == 2
    engine.dispose()


def test_create_super_admin_rejects_cross_company_username_and_weak_password():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(name="第一公司", code="FIRST", status="ACTIVE")
        db.add(company)
        db.flush()
        db.add(
            User(
                company_id=company.id,
                username="taken",
                password_hash="unused",
                real_name="已有账号",
                role_ids=[],
                status="ACTIVE",
            )
        )
        db.flush()
        try:
            ensure_super_admin(
                db,
                company_code="SECOND",
                company_name="第二公司",
                username="taken",
                password="Strong@2026",
            )
        except BusinessRuleError as exc:
            assert "其他公司" in str(exc) or "已存在" in str(exc)
        else:
            raise AssertionError("不得跨公司接管用户名")
        assert db.execute(select(Company).where(Company.code == "SECOND")).scalar_one_or_none() is None

        try:
            ensure_super_admin(
                db,
                company_code="THIRD",
                company_name="第三公司",
                username="newadmin",
                password="weak",
            )
        except BusinessRuleError as exc:
            assert "密码" in str(exc)
        else:
            raise AssertionError("弱密码必须被拒绝")
        assert db.execute(select(Company).where(Company.code == "THIRD")).scalar_one_or_none() is None
        assert db.execute(select(func.count()).select_from(Permission)).scalar_one() == 0
    engine.dispose()


def test_create_super_admin_requires_migrated_schema():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as db:
        try:
            ensure_super_admin(
                db,
                company_code="EOMS",
                company_name="示例公司",
                username="admin",
                password="Strong@2026",
            )
        except BusinessRuleError as exc:
            assert "alembic upgrade head" in str(exc)
        else:
            raise AssertionError("缺少数据表时应给出迁移提示")
    engine.dispose()
