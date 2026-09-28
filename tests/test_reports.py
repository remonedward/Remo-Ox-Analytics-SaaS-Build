from __future__ import annotations

"""Unit tests for analytics/reports.py."""

import pandas as pd

from analytics.engine import DatasetContext
from analytics.reports import (
    expense_breakdown,
    receivables_aging,
    run_report,
    sales_overview,
    slow_inventory,
    top_products,
)
from analytics.schemas import QualitySummary, RunReportInput


def test_sales_overview_report(sales_context: DatasetContext) -> None:
    """sales_overview computes monthly numbers and KPI cards."""
    res = sales_overview(sales_context)
    assert res.report_id == "sales_overview"
    assert not res.missing_roles
    assert len(res.kpis) >= 3
    # Verify monthly table exists
    assert "monthly_sales" in res.tables
    table = res.tables["monthly_sales"]
    assert len(table.data) >= 1
    # Total revenue in our fixture is 6250
    assert table.data[0]["revenue"] == 6250.0


def test_sales_overview_missing_roles() -> None:
    """sales_overview returns missing_roles when required fields not mapped."""
    dummy_df = pd.DataFrame({"a": [1, 2]})
    ctx = DatasetContext(
        sheets={"Sales": dummy_df},
        mapping={},
        quality_summary={"Sales": QualitySummary(sheet_name="Sales", row_count=len(dummy_df))},
    )
    res = sales_overview(ctx)
    assert len(res.missing_roles) > 0
    assert any("date" in r for r in res.missing_roles)


def test_top_products_report(sales_context: DatasetContext) -> None:
    """top_products calculates ranking, Pareto 80/20, and profit."""
    res = top_products(sales_context)
    assert res.report_id == "top_products"
    assert "top_products" in res.tables
    table = res.tables["top_products"]
    # Top product is Laptop (5000 revenue)
    assert table.data[0]["product"] == "Laptop"
    assert table.data[0]["revenue"] == 5000.0
    # Profit calculation check (cost for Laptop: 700*1 + 1400*2 + 700*1 + 700*1 = 3500)
    # Profit: 5000 - 3500 = 1500
    assert table.data[0]["profit"] == 1500.0
    # Pareto count KPI
    pareto_kpi = next(k for k in res.kpis if "Pareto" in k.label)
    assert "1 SKUs" in pareto_kpi.value  # Laptop makes 80% alone


def test_slow_inventory_report(inventory_df: pd.DataFrame) -> None:
    """slow_inventory identifies items inactive beyond threshold."""
    ctx = DatasetContext(
        sheets={"Inventory": inventory_df},
        mapping={
            "product": "product",
            "stock_qty": "stock_qty",
            "unit_cost": "unit_cost",
            "last_movement_date": "last_movement_date",
        },
        quality_summary={"Inventory": QualitySummary(sheet_name="Inventory", row_count=len(inventory_df))},
    )
    res = slow_inventory(ctx, params={"slow_days_threshold": 90})
    assert res.report_id == "slow_inventory"
    assert "slow_items" in res.tables
    table = res.tables["slow_items"]
    # Widget A (2023-01-01) and Widget D (2023-06-01) are > 90 days inactive
    slow_prods = [r["product"] for r in table.data]
    assert "Widget A" in slow_prods
    assert "Widget D" in slow_prods
    # Widget C has 0 stock, so it shouldn't be counted in positive slow stock
    assert "Widget C" not in slow_prods


def test_receivables_aging_report(receivables_df: pd.DataFrame) -> None:
    """receivables_aging categorizes invoices into aging buckets."""
    ctx = DatasetContext(
        sheets={"Receivables": receivables_df},
        mapping={
            "customer": "customer",
            "invoice_amount": "invoice_amount",
            "paid_amount": "paid_amount",
            "due_date": "due_date",
        },
        quality_summary={"Receivables": QualitySummary(sheet_name="Receivables", row_count=len(receivables_df))},
    )
    res = receivables_aging(ctx)
    assert res.report_id == "receivables_aging"
    assert "aging_summary" in res.tables
    assert "top_overdue_customers" in res.tables
    # Check total outstanding: (5000-1000) + (2000-2000) + (3000-0) + (1500-500) = 4000 + 0 + 3000 + 1000 = 8000
    aging_table = res.tables["aging_summary"]
    total_amount = sum(r["amount"] for r in aging_table.data)
    assert total_amount == 8000.0


def test_expense_breakdown_report(expenses_df: pd.DataFrame) -> None:
    """expense_breakdown computes category totals and shares."""
    ctx = DatasetContext(
        sheets={"Expenses": expenses_df},
        mapping={
            "category": "category",
            "expense_amount": "expense_amount",
            "date": "date",
        },
        quality_summary={"Expenses": QualitySummary(sheet_name="Expenses", row_count=len(expenses_df))},
    )
    res = expense_breakdown(ctx)
    assert res.report_id == "expense_breakdown"
    assert "expenses_by_category" in res.tables
    assert "monthly_expenses" in res.tables
    table = res.tables["expenses_by_category"]
    # Total: 5000 + 12000 + 5000 + 3000 + 800 = 25800
    # Salaries: 12000 (top), Rent: 10000 (second)
    assert table.data[0]["category"] == "Salaries"
    assert table.data[0]["total_amount"] == 12000.0
    assert table.data[1]["category"] == "Rent"
    assert table.data[1]["total_amount"] == 10000.0


def test_run_report_dispatcher(sales_context: DatasetContext) -> None:
    """run_report properly dispatches to the requested report."""
    inp = RunReportInput(report_id="sales_overview")
    res = run_report(sales_context, inp)
    assert res.report_id == "sales_overview"
    assert res.error is None
