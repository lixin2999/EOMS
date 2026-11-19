"""finance concurrency hardening

Revision ID: a1f7c2d9e4b6
Revises: 4053432b8727
Create Date: 2026-11-19

1) ``fin_payment``：同一报销单在 PENDING/PAID 状态下只允许一张付款单（部分唯一索引），
   从数据库层兜住「报销付款单可重复创建」。
2) ``fin_pending_cost``：期间关账后的成本暂存表，反关账或定时任务再补记到
   ``fin_cost_record``（按 ``record_key`` 幂等）。
3) ``fin_pending_cost`` 纳入 PostgreSQL 行级安全（SQLite 自动跳过）。

升级前排查重复数据，否则唯一索引创建会失败：

    SELECT expense_id, count(*) FROM fin_payment
    WHERE expense_id IS NOT NULL AND status IN ('PENDING', 'PAID')
    GROUP BY expense_id HAVING count(*) > 1;

若存在重复，需先人工作废多余付款单（保留一条）后再执行升级。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1f7c2d9e4b6"
down_revision: str | None = "4053432b8727"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = """
CREATE POLICY eoms_tenant_isolation ON {table}
USING (
    current_setting('app.bypass', true) = 'on'
    OR current_setting('app.scope_all', true) = '1'
    OR company_id = nullif(current_setting('app.company_id', true), '')::int
)
"""

PAYMENT_ACTIVE_WHERE = "expense_id IS NOT NULL AND status IN ('PENDING', 'PAID')"


def upgrade() -> None:
    op.create_table(
        "fin_pending_cost",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("record_key", sa.String(length=160), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("dept_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("biz_type", sa.String(length=16), nullable=False),
        sa.Column("biz_id", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("occur_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("applicant_id", sa.Integer(), nullable=True),
        sa.Column("source_no", sa.String(length=64), nullable=True),
        sa.Column("cash_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("cost_record_id", sa.Integer(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_pending_cost")),
        sa.UniqueConstraint("record_key", name="uq_fin_pending_cost_record_key"),
    )
    op.create_index(op.f("ix_fin_pending_cost_company_id"), "fin_pending_cost", ["company_id"], unique=False)
    op.create_index(op.f("ix_fin_pending_cost_period"), "fin_pending_cost", ["period"], unique=False)
    op.create_index(
        "ix_fin_pending_cost_company_status",
        "fin_pending_cost",
        ["company_id", "status", "period"],
        unique=False,
    )

    op.create_index(
        "uq_fin_payment_expense_active",
        "fin_payment",
        ["expense_id"],
        unique=True,
        postgresql_where=sa.text(PAYMENT_ACTIVE_WHERE),
        sqlite_where=sa.text(PAYMENT_ACTIVE_WHERE),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE fin_pending_cost ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE fin_pending_cost FORCE ROW LEVEL SECURITY")
        op.execute(POLICY.format(table="fin_pending_cost"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS eoms_tenant_isolation ON fin_pending_cost")

    op.drop_index("uq_fin_payment_expense_active", table_name="fin_payment")
    op.drop_index("ix_fin_pending_cost_company_status", table_name="fin_pending_cost")
    op.drop_index(op.f("ix_fin_pending_cost_period"), table_name="fin_pending_cost")
    op.drop_index(op.f("ix_fin_pending_cost_company_id"), table_name="fin_pending_cost")
    op.drop_table("fin_pending_cost")