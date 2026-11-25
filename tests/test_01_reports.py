"""报表口径回归：演示数据固定数值，验证 Decimal 汇总与统一口径。"""

from __future__ import annotations

import pytest

REPORTS = "/api/v1/reports"


@pytest.mark.parametrize(
    ("code", "keys"),
    [
        ("OVERVIEW", {"revenue", "cost", "gross_profit", "receipt", "receivable_balance", "project_count"}),
        ("REVENUE", {"total", "items"}),
        ("CASHFLOW", {"total_inflow", "total_outflow", "net"}),
        ("PROFIT", {"revenue", "cost", "profit"}),
        ("PROJECT_PNL", {"items"}),
        ("VENDOR_SPEND", {"items"}),
        ("APPROVAL_EFFICIENCY", {"items"}),
    ],
)
def test_report_catalog_available(client, auth, code, keys):
    response = client.get(
        f"{REPORTS}/{code}",
        params={"start": "2026-01-01", "end": "2026-12-31"},
        headers=auth("director"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0
    assert keys.issubset(body["data"].keys())


@pytest.mark.parametrize(
    ("group_by", "dimension", "expected_items"),
    [("period", "period", 6), ("project", "project_id", 3), ("customer", "customer_id", 3)],
)
def test_revenue_report_aggregates_selected_dimension(client, auth, group_by, dimension, expected_items):
    response = client.get(
        f"{REPORTS}/REVENUE",
        params={"start": "2026-01", "end": "2026-12", "group_by": group_by},
        headers=auth("director"),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["group_by"] == group_by
    assert data["total"] == 4_400_000
    assert len(data["items"]) == expected_items
    assert sum(item["amount"] for item in data["items"]) == pytest.approx(data["total"])
    assert sum(item["count"] for item in data["items"]) == 6
    assert len({item["key"] for item in data["items"]}) == expected_items
    for item in data["items"]:
        for field in ("period", "project_id", "customer_id"):
            if field == dimension:
                assert item[field] is not None
            else:
                assert item[field] is None


@pytest.mark.parametrize(
    ("group_by", "column"),
    [("period", "period"), ("project", "project_id"), ("customer", "customer_id")],
)
def test_revenue_report_postgresql_grouping_matches_selected_dimension(group_by, column):
    from unittest.mock import Mock

    from sqlalchemy.dialects import postgresql

    from app.core.scope import ScopeContext
    from app.services.report.metrics import revenue_report

    db = Mock()
    db.execute.return_value.all.return_value = []
    ctx = ScopeContext(user_id=0, company_id=1, dept_id=None, is_super=True, scopes={"ALL"})
    revenue_report(db, ctx, start="2026-11", end="2026-11", group_by=group_by)

    stmt = db.execute.call_args.args[0]
    assert len(stmt.selected_columns) == 3
    assert stmt.selected_columns[0].name == column
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert f"GROUP BY fin_revenue_confirm.{column}" in sql


def test_overview_matches_seed_figures(client, auth):
    response = client.get(f"{REPORTS}/OVERVIEW", params={"year": 2026}, headers=auth("director"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["revenue"] == 4_400_000
    assert data["cost"] == 1_421_060
    assert data["gross_profit"] == 2_978_940
    assert data["gross_profit"] == data["revenue"] - data["cost"]
    assert data["receipt"] == 4_300_000
    assert data["receivable_balance"] == 100_000
    assert data["project_count"] == 4
    assert isinstance(data["monthly"], list) and len(data["monthly"]) >= 10


def test_cashflow_net_matches_receipts_minus_payments(client, auth):
    response = client.get(
        f"{REPORTS}/CASHFLOW",
        params={"start": "2026-01-01", "end": "2026-12-31"},
        headers=auth("director"),
    )
    data = response.json()["data"]
    assert data["total_inflow"] == 4_300_000
    assert data["net"] == data["total_inflow"] - data["total_outflow"]
    assert data["net"] == pytest.approx(2_878_940, abs=1)


def test_project_pnl_snapshot_is_cumulative(client, auth, demo):
    project_id = sorted(demo["project_ids"])[0]
    response = client.get(
        f"{REPORTS}/PROJECT_PNL",
        params={"start": "2026-01-01", "end": "2026-12-31", "project_id": project_id},
        headers=auth("director"),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items, "项目损益应有快照记录"
    row = items[0]
    assert row["project_id"] == project_id
    assert float(row["revenue"]) == 2_200_000
    assert float(row["cost"]) == 1_050_000
    assert float(row["gross_profit"]) == 1_150_000


def test_report_permission_denied_for_employee(client, auth):
    response = client.get(f"{REPORTS}/OVERVIEW", params={"year": 2026}, headers=auth("employee"))
    assert response.status_code == 403
    assert response.json()["code"] != 0
