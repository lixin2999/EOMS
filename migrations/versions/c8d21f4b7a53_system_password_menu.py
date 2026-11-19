"""system password menu

Revision ID: c8d21f4b7a53
Revises: b7e3d5a10c48
Create Date: 2026-11-19

「系统管理」新增「修改密码」菜单（system:password），并使既有库的系统管理员角色
自动获得该权限点。脚本对空库/已存在的记录保持幂等（重复执行不会产生重复行）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d21f4b7a53"
down_revision: str | None = "b7e3d5a10c48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "system:password"


def _scalar(conn, sql: str, **params):
    return conn.execute(sa.text(sql), params).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    parent_id = _scalar(conn, "SELECT id FROM sys_permission WHERE code = 'menu:system'")
    if parent_id is None:
        # 权限点尚未初始化（空库），由 scripts.seed 负责整体写入。
        return
    permission_id = _scalar(conn, "SELECT id FROM sys_permission WHERE code = :code", code=PERMISSION_CODE)
    if permission_id is None:
        conn.execute(
            sa.text(
                "INSERT INTO sys_permission (code, name, type, parent_id, path, component, icon, sort, visible) "
                "VALUES (:code, :name, 'menu', :parent_id, :path, :component, :icon, :sort, :visible)"
            ),
            {
                "code": PERMISSION_CODE,
                "name": "修改密码",
                "parent_id": parent_id,
                "path": "/system/password",
                "component": "system/Password",
                "icon": "Lock",
                "sort": 97,
                "visible": True,
            },
        )
        permission_id = _scalar(conn, "SELECT id FROM sys_permission WHERE code = :code", code=PERMISSION_CODE)
    admin_role_id = _scalar(conn, "SELECT id FROM sys_role WHERE code = 'ADMIN'")
    if admin_role_id is None or permission_id is None:
        return
    granted = _scalar(
        conn,
        "SELECT id FROM sys_role_permission WHERE role_id = :role_id AND permission_id = :permission_id",
        role_id=admin_role_id,
        permission_id=permission_id,
    )
    if granted is None:
        conn.execute(
            sa.text("INSERT INTO sys_role_permission (role_id, permission_id) VALUES (:role_id, :permission_id)"),
            {"role_id": admin_role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    permission_id = _scalar(conn, "SELECT id FROM sys_permission WHERE code = :code", code=PERMISSION_CODE)
    if permission_id is None:
        return
    conn.execute(
        sa.text("DELETE FROM sys_role_permission WHERE permission_id = :permission_id"),
        {"permission_id": permission_id},
    )
    conn.execute(sa.text("DELETE FROM sys_permission WHERE id = :permission_id"), {"permission_id": permission_id})
