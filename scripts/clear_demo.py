"""安全清理 DEMO 演示租户。

默认只统计将要删除的数据；显式传入 ``--yes`` 才会执行。
仅删除公司编码为 ``DEMO`` 的租户数据，保留全局权限、内置角色、系统参数和其他公司。
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import ColumnElement, Table, delete, func, inspect, or_, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: E402,F401  确保全部模型注册到 Base.metadata
from app.core.cache import cache
from app.core.errors import BusinessRuleError
from app.db.base import Base
from app.db.session import session_scope
from app.models.approval import Expense, ExpenseItem
from app.models.iam import Company, Role, RolePermission, SysFile, User
from app.models.platform import Sequence
from app.models.project import Project, TaskBaseline
from app.services.storage import delete_object

DEMO_COMPANY_CODE = "DEMO"


@dataclass
class CleanupResult:
    company_id: int
    counts: dict[str, int] = field(default_factory=dict)
    user_ids: list[int] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    file_keys: list[str] = field(default_factory=list)
    shared_file_keys: list[str] = field(default_factory=list)
    demo_file_count: int = 0


def _tenant_tables() -> list[Table]:
    return [
        table
        for table in Base.metadata.sorted_tables
        if "company_id" in table.c and table.name != Company.__tablename__
    ]


def _count(db: Session, table: Table, condition: ColumnElement[bool]) -> int:
    return int(db.execute(select(func.count()).select_from(table).where(condition)).scalar_one())


def _require_schema(db: Session) -> None:
    required = {
        Company.__tablename__,
        User.__tablename__,
        SysFile.__tablename__,
        Expense.__tablename__,
        ExpenseItem.__tablename__,
        Project.__tablename__,
        TaskBaseline.__tablename__,
        Role.__tablename__,
        RolePermission.__tablename__,
        Sequence.__tablename__,
        *(table.name for table in _tenant_tables()),
    }
    available = set(inspect(db.connection()).get_table_names())
    missing = sorted(required - available)
    if missing:
        raise BusinessRuleError(f"数据库结构不完整，缺少表：{', '.join(missing)}；请先执行 alembic upgrade head")


def clear_demo_data(db: Session, *, execute: bool = False) -> CleanupResult | None:
    """统计或删除 DEMO 租户；事务提交由调用方负责。"""
    _require_schema(db)
    company = db.execute(select(Company).where(Company.code == DEMO_COMPANY_CODE)).scalar_one_or_none()
    if company is None:
        return None

    company_id = company.id
    users = list(db.execute(select(User).where(User.company_id == company_id)).scalars())
    demo_paths = set(db.execute(select(SysFile.path).where(SysFile.company_id == company_id)).scalars())
    shared_paths = set(
        db.execute(
            select(SysFile.path).where(or_(SysFile.company_id != company_id, SysFile.company_id.is_(None)))
        ).scalars()
    )
    result = CleanupResult(
        company_id=company_id,
        user_ids=[user.id for user in users],
        usernames=[user.username for user in users],
        file_keys=sorted(demo_paths - shared_paths),
        shared_file_keys=sorted(demo_paths & shared_paths),
        demo_file_count=len(demo_paths),
    )

    expense_ids = select(Expense.id).where(Expense.company_id == company_id)
    project_ids = select(Project.id).where(Project.company_id == company_id)
    role_ids = select(Role.id).where(Role.company_id == company_id)
    sequence_filter = Sequence.name.like(f"%:{company.code}")

    special: list[tuple[str, ColumnElement[bool]]] = [
        (ExpenseItem.__tablename__, ExpenseItem.expense_id.in_(expense_ids)),
        (TaskBaseline.__tablename__, TaskBaseline.project_id.in_(project_ids)),
        (RolePermission.__tablename__, RolePermission.role_id.in_(role_ids)),
    ]
    for table_name, condition in special:
        table = Base.metadata.tables[table_name]
        result.counts[table_name] = _count(db, table, condition)

    for table in _tenant_tables():
        result.counts[table.name] = _count(db, table, table.c.company_id == company_id)

    result.counts[Sequence.__tablename__] = _count(db, Base.metadata.tables[Sequence.__tablename__], sequence_filter)
    result.counts[Company.__tablename__] = 1

    if not execute:
        return result

    # 先删除没有 company_id 的子表/关联表，再按模型依赖逆序删除租户表。
    for table_name, condition in special:
        db.execute(delete(Base.metadata.tables[table_name]).where(condition))
    for table in reversed(_tenant_tables()):
        db.execute(delete(table).where(table.c.company_id == company_id))
    db.execute(delete(Sequence).where(sequence_filter))
    db.execute(delete(Company).where(Company.id == company_id))
    db.flush()
    return result


def _clear_runtime_state(result: CleanupResult) -> None:
    for user_id, username in zip(result.user_ids, result.usernames, strict=True):
        cache.delete(f"perm:{user_id}", f"sess:{user_id}", f"lock:sess:{user_id}", f"login:fail:{username.lower()}")
        cache.delete_prefix(f"idem:{result.company_id}:{user_id}:")
        cache.delete_prefix(f"idem-lock:idem:{result.company_id}:{user_id}:")


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 EOMS DEMO 演示租户（默认预演）")
    parser.add_argument("--yes", action="store_true", help="确认执行删除；不加此参数仅统计")
    parser.add_argument("--keep-files", action="store_true", help="保留对象存储中的演示附件，仅清理数据库")
    args = parser.parse_args()

    try:
        with session_scope() as db:
            result = clear_demo_data(db, execute=args.yes)
    except BusinessRuleError as exc:
        raise SystemExit(f"[clear-demo] {exc}") from exc

    if result is None:
        print(f"[clear-demo] 未找到公司编码为 {DEMO_COMPANY_CODE} 的演示租户，无需清理")
        return

    print(f"[clear-demo] 公司：{DEMO_COMPANY_CODE}（ID={result.company_id}）")
    for table_name, count in result.counts.items():
        if count:
            print(f"  {table_name}: {count}")

    if not args.yes:
        print(
            f"[clear-demo] 对象存储：将删除 {len(result.file_keys)} 个附件，"
            f"保留 {len(result.shared_file_keys)} 个其他租户仍在引用的共享对象"
        )
        print("[clear-demo] 当前为预演，未删除任何数据。确认备份后添加 --yes 执行。")
        return

    _clear_runtime_state(result)
    if not args.keep_files:
        for key in result.file_keys:
            delete_object(key)
        print(f"[clear-demo] 已处理 {len(result.file_keys)} 个演示附件对象的删除")
    else:
        print(f"[clear-demo] 已保留 {result.demo_file_count} 个演示附件对象（--keep-files）")
    if result.shared_file_keys:
        print(f"[clear-demo] 已保留 {len(result.shared_file_keys)} 个其他租户仍在引用的共享对象")
    print("[clear-demo] DEMO 演示租户清理完成；全局权限、内置角色、系统参数和其他公司数据均保留")


if __name__ == "__main__":
    main()
