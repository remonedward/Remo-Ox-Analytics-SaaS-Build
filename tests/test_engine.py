from __future__ import annotations

"""Unit tests for analytics/engine.py."""

import pandas as pd
import pytest

from analytics.engine import (
    DatasetContext,
    EngineError,
    aggregate,
    bottom_n,
    compare_periods,
    data_quality_report,
    describe_column,
    get_schema,
    top_n,
)
from analytics.schemas import (
    AggregateInput,
    ComparePeriodInput,
    DescribeColumnInput,
    MetricSpec,
    PeriodSpec,
    QualitySummary,
    SafeFilter,
    TopNInput,
)


def test_get_schema(sales_context: DatasetContext) -> None:
    """get_schema returns column types, mapped roles, and row counts."""
    res = get_schema(sales_context)
    assert len(res.sheets) == 1
    sheet = res.sheets[0]
    assert sheet.sheet_name == "Sales"
    assert sheet.row_count == 10
    col_names = [c.name for c in sheet.columns]
    assert "revenue" in col_names
    rev_col = next(c for c in sheet.columns if c.name == "revenue")
    assert rev_col.mapped_role == "revenue"


def test_aggregate_group_by_sum(sales_context: DatasetContext) -> None:
    """aggregate computes correct sums grouped by category."""
    inp = AggregateInput(
        sheet_name="Sales",
        group_by=["category"],
        metrics=[
            MetricSpec(column="revenue", agg="sum"),
            MetricSpec(column="quantity", agg="sum"),
        ],
        sort_by="revenue_sum",
        sort_desc=True,
    )
    res = aggregate(sales_context, inp)
    assert len(res.data) == 2  # Tech, Accessories
    top_row = res.data[0]
    assert top_row["category"] == "Tech"
    # Tech revenue: 1000 + 2000 + 1000 + 300 + 600 + 1000 = 5900
    assert top_row["revenue_sum"] == 5900.0


def test_aggregate_ungrouped(sales_context: DatasetContext) -> None:
    """aggregate without group_by returns single overall total row."""
    inp = AggregateInput(
        sheet_name="Sales",
        group_by=[],
        metrics=[MetricSpec(column="revenue", agg="sum")],
    )
    res = aggregate(sales_context, inp)
    assert len(res.data) == 1
    # Total revenue: 1000 + 50 + 2000 + 75 + 75 + 1000 + 300 + 600 + 1000 + 150 = 6250
    assert res.data[0]["revenue_sum"] == 6250.0


def test_aggregate_with_filter(sales_context: DatasetContext) -> None:
    """aggregate applies safe filters before aggregation."""
    inp = AggregateInput(
        sheet_name="Sales",
        group_by=["product"],
        metrics=[MetricSpec(column="revenue", agg="sum")],
        filters=[SafeFilter(column="customer", op="eq", value="Alice")],
    )
    res = aggregate(sales_context, inp)
    # Alice bought: Laptop (1000), Laptop (2000), Monitor (300), Keyboard (150)
    prods = {r["product"]: r["revenue_sum"] for r in res.data}
    assert prods["Laptop"] == 3000.0
    assert prods["Monitor"] == 300.0
    assert prods["Keyboard"] == 150.0


def test_top_n_and_pareto(sales_context: DatasetContext) -> None:
    """top_n returns ordered results with share_of_total and cumulative_share."""
    inp = TopNInput(
        sheet_name="Sales",
        category_column="product",
        metric=MetricSpec(column="revenue", agg="sum"),
        n=3,
    )
    res = top_n(sales_context, inp)
    assert len(res.data) <= 3
    assert res.data[0]["product"] == "Laptop"  # 5000 / 6250 = 80.0%
    assert round(res.data[0]["share_of_total"], 1) == 80.0
    assert round(res.data[0]["cumulative_share"], 1) == 80.0


def test_bottom_n(sales_context: DatasetContext) -> None:
    """bottom_n orders ascending by metric."""
    inp = TopNInput(
        sheet_name="Sales",
        category_column="product",
        metric=MetricSpec(column="revenue", agg="sum"),
        n=2,
        descending=False,
    )
    res = bottom_n(sales_context, inp)
    assert res.data[0]["revenue_sum"] <= res.data[1]["revenue_sum"]


def test_compare_periods() -> None:
    """compare_periods correctly computes abs and pct delta."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-10", "2024-02-05", "2024-02-10"]),
            "revenue": [100.0, 200.0, 150.0, 250.0],
        }
    )
    ctx = DatasetContext(
        sheets={"Sales": df},
        mapping={"date": "date", "revenue": "revenue"},
        quality_summary={"Sales": QualitySummary(sheet_name="Sales", row_count=len(df))},
    )
    inp = ComparePeriodInput(
        sheet_name="Sales",
        metric=MetricSpec(column="revenue", agg="sum"),
        period_a=PeriodSpec(date_column="date", start="2024-01-01", end="2024-01-31"),
        period_b=PeriodSpec(date_column="date", start="2024-02-01", end="2024-02-28"),
    )
    res = compare_periods(ctx, inp)
    row = res.data[0]
    # Period A: 100 + 200 = 300
    # Period B: 150 + 250 = 400
    assert row["abs_change"] == 100.0
    assert round(row["pct_change"], 2) == round((100.0 / 300.0) * 100, 2)


def test_describe_column(sales_context: DatasetContext) -> None:
    """describe_column returns stats for numeric and text columns."""
    num_res = describe_column(
        sales_context, DescribeColumnInput(sheet_name="Sales", column="revenue")
    )
    assert len(num_res.data) > 0
    stat_keys = [r["statistic"] for r in num_res.data]
    assert "mean" in stat_keys
    assert "min" in stat_keys
    assert "max" in stat_keys

    cat_res = describe_column(
        sales_context, DescribeColumnInput(sheet_name="Sales", column="product")
    )
    cat_keys = [r["statistic"] for r in cat_res.data]
    assert "unique_count" in cat_keys


def test_result_truncation() -> None:
    """Large datasets are truncated at 50 rows in ToolResult."""
    large_df = pd.DataFrame(
        {"item": [f"Item_{i}" for i in range(100)], "val": list(range(100))}
    )
    ctx = DatasetContext(
        sheets={"Large": large_df},
        mapping={},
        quality_summary={"Large": QualitySummary(sheet_name="Large", row_count=len(large_df))},
    )
    inp = AggregateInput(
        sheet_name="Large",
        group_by=["item"],
        metrics=[MetricSpec(column="val", agg="sum")],
        limit=50,
    )
    res = aggregate(ctx, inp)
    assert len(res.data) <= 50
    assert res.total_rows == 100
    assert res.truncated is True


def test_preview_rows(sales_context: DatasetContext) -> None:
    """preview_rows returns raw rows within limit when enabled."""
    sales_context.send_sample_rows = True
    from analytics.engine import preview_rows
    from analytics.schemas import PreviewRowsInput
    res = preview_rows(sales_context, PreviewRowsInput(sheet_name="Sales", limit=3))
    assert len(res.data) == 3
    assert "Laptop" in str(res.data[0])


def test_preview_rows_disabled(sales_context: DatasetContext) -> None:
    """preview_rows returns error in ToolResult when send_sample_rows is False."""
    sales_context.send_sample_rows = False
    from analytics.engine import preview_rows
    from analytics.schemas import PreviewRowsInput
    res = preview_rows(sales_context, PreviewRowsInput(sheet_name="Sales", limit=3))
    assert res.error is not None
    assert "privacy" in res.error.lower() or "disabled" in res.error.lower()


def test_data_quality_report_engine(sales_context: DatasetContext) -> None:
    """data_quality_report returns tabular quality metrics."""
    res = data_quality_report(sales_context)
    assert len(res.data) >= 1
    assert "sheet_name" in res.data[0] or "sheet" in res.data[0] or "metric" in res.data[0] or "row_count" in res.data[0]


def test_aggregate_date_grain_month(sales_context: DatasetContext) -> None:
    """aggregate with date_grain groups properly."""
    inp = AggregateInput(
        sheet_name="Sales",
        date_column="date",
        date_grain="month",
        metrics=[MetricSpec(column="revenue", agg="sum")],
    )
    res = aggregate(sales_context, inp)
    assert len(res.data) == 1
    assert res.data[0]["revenue_sum"] == 6250.0


def test_engine_errors(sales_context: DatasetContext) -> None:
    """Engine raises clear EngineError on missing sheets or unmapped roles."""
    with pytest.raises(EngineError):
        sales_context.get_sheet("NonExistent")

    with pytest.raises(EngineError):
        sales_context.require_role("unmapped_role_xyz")

