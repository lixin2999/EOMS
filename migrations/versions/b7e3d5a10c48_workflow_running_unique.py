"""workflow running unique

Revision ID: b7e3d5a10c48
Revises: a1f7c2d9e4b6
Create Date: 2026-11-19

同一公司、同一业务单据只允许存在一个 RUNNING 流程实例（部分唯一索引），
从数据库层兜住并发提交重复起流程。

⚠️ 升级前置检查：存量若存在重复 RUNNING 实例，索引创建会失败。先执行

    SELECT company_id, biz_type, biz_id, count(*) FROM wf_instance
    WHERE status = 'RUNNING'
    GROUP BY company_id, biz_type, biz_id HAVING count(*) > 1;

如有结果，需先人工关停/终止多余实例（每个业务单据仅保留一条 RUNNING），
再执行 ``alembic upgrade head``。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3d5a10c48"
down_revision: str | None = "a1f7c2d9e4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_wf_instance_biz_running",
        "wf_instance",
        ["company_id", "biz_type", "biz_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
        sqlite_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_wf_instance_biz_running", table_name="wf_instance")