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
