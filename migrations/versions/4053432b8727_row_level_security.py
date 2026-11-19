"""row level security

Revision ID: 4053432b8727
Revises: c463c99b405d
Create Date: 2026-11-16

PostgreSQL 行级安全兜底：所有业务表按 company_id 收敛，应用层通过
set_config('app.company_id'/'app.bypass', ...) 注入当前租户。
SQLite（本地开发）自动跳过。

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "4053432b8727"
down_revision: str | None = "c463c99b405d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "biz_document",
    "biz_expense",
    "biz_leave",
    "biz_leave_balance",
    "fin_account",
    "fin_budget",
    "fin_cost_record",
    "fin_payment",
    "fin_period",
    "fin_project_pnl",
    "fin_receipt",
    "fin_revenue_confirm",
    "pm_acceptance",
    "pm_change",
    "pm_initiation",
    "pm_issue",
    "pm_milestone",
    "pm_project",
    "pm_project_archive",
    "pm_project_member",
    "pm_report",
    "pm_risk",
    "pm_task",
    "pm_wbs",
    "rpt_snapshot",
    "sys_file",
    "sys_notification",
    "vd_contract",
    "vd_evaluation",
    "vd_vendor",
    "vd_vendor_bank",
    "vd_vendor_contact",
    "vd_vendor_license",
    "vd_vendor_project",
    "wf_cc",
    "wf_definition",
    "wf_instance",
    "wf_record",
    "wf_task",
]

POLICY = """
CREATE POLICY eoms_tenant_isolation ON {table}
USING (
    current_setting('app.bypass', true) = 'on'
    OR current_setting('app.scope_all', true) = '1'
    OR company_id = nullif(current_setting('app.company_id', true), '')::int
)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(POLICY.format(table=table))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS eoms_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
