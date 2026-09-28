from __future__ import annotations

"""Unit tests for data/quality.py."""

import numpy as np
import pandas as pd

from data.quality import generate_quality_report, get_summary_text


def test_generate_quality_report_clean_data(simple_sales_df: pd.DataFrame) -> None:
    """Quality report on clean data generates zero parse failures and accurate row count."""
    mapping = {
        "date": "date",
        "product": "product",
        "revenue": "revenue",
    }
    report = generate_quality_report({"Sales": simple_sales_df}, mapping)
    sheet_map = {s.sheet_name: s for s in report.sheets}
    assert "Sales" in sheet_map
    sheet_rep = sheet_map["Sales"]
    assert sheet_rep.row_count == len(simple_sales_df)
    assert sheet_rep.duplicate_rows == 0

    # Summary text in Arabic and English
    ar_summary = get_summary_text(report, "Sales", lang="ar")
    en_summary = get_summary_text(report, "Sales", lang="en")
    assert len(ar_summary) > 0
    assert len(en_summary) > 0


def test_generate_quality_report_with_issues() -> None:
    """Quality report detects nulls, outliers, and duplicate rows."""
    df = pd.DataFrame(
        {
            "product": ["Item A", "Item B", "Item A", "Item C", "Item D"],
            "stock_qty": [10, -5, 10, 1000, np.nan],  # negative value, outlier, null
            "price": [100.0, 120.0, 100.0, 150.0, 110.0],
        }
    )
    # Row 0 and 2 are identical
    mapping = {"product": "product", "stock_qty": "stock_qty", "unit_price": "price"}
    report = generate_quality_report({"Inventory": df}, mapping)
    sheet_map = {s.sheet_name: s for s in report.sheets}
    assert "Inventory" in sheet_map
    sheet_rep = sheet_map["Inventory"]

    assert sheet_rep.duplicate_rows == 1

    col_reps = {c.column: c for c in sheet_rep.columns}
    stock_rep = col_reps["stock_qty"]
    assert stock_rep.null_count == 1
    assert stock_rep.negative_count == 1
    assert stock_rep.outliers_count >= 1

    summary_ar = get_summary_text(report, "Inventory", lang="ar")
    assert len(summary_ar) > 0
