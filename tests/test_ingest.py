from __future__ import annotations

"""Unit tests for data/ingest.py."""

from pathlib import Path

import pandas as pd

from data.ingest import (
    _deduplicate_columns,
    _is_total_row,
    _normalize_arabic_digits,
    read_excel,
)

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def test_normalize_arabic_digits() -> None:
    """Arabic-Indic numerals (٠-٩) are converted to Western (0-9)."""
    text = "السعر: ١٢٥٠.٥٠ جنيه"
    res = _normalize_arabic_digits(text)
    assert "1250.50" in res


def test_deduplicate_columns() -> None:
    """Duplicate column names are safely suffixed."""
    cols = ["date", "sales", "sales", "date", "sales"]
    deduped = _deduplicate_columns(cols)
    assert deduped == ["date", "sales", "sales_2", "date_2", "sales_3"]


def test_is_total_row() -> None:
    """Summary and total rows in Arabic and English are detected."""
    s1 = pd.Series(["الإجمالي", 100, 200])
    assert _is_total_row(s1) is True

    s2 = pd.Series(["Total", 500, 1000])
    assert _is_total_row(s2) is True

    s3 = pd.Series(["المجموع العام", 450])
    assert _is_total_row(s3) is True

    s4 = pd.Series(["Laptop", 2, 2000])
    assert _is_total_row(s4) is False


def test_read_excel_clean_english() -> None:
    """read_excel reads and cleans English sample workbook."""
    file_path = SAMPLE_DIR / "sales_en.xlsx"
    assert file_path.exists(), "Sample file sales_en.xlsx missing"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    res = read_excel(file_bytes)
    assert "Sales" in res.sheets
    df = res.sheets["Sales"]
    assert len(df) == 300
    assert "Date" in df.columns
    assert "Revenue" in df.columns
    # Check numeric conversion
    assert pd.api.types.is_numeric_dtype(df["Revenue"])


def test_read_excel_messy_arabic() -> None:
    """read_excel detects header, strips totals, and normalizes Arabic file."""
    file_path = SAMPLE_DIR / "sales_ar.xlsx"
    assert file_path.exists(), "Sample file sales_ar.xlsx missing"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    res = read_excel(file_bytes)
    assert "المبيعات" in res.sheets
    df = res.sheets["المبيعات"]
    # Header was on row 4 (0-based index 3)
    assert res.header_rows["المبيعات"] == 3
    # Excluded summary rows should be captured
    assert len(res.excluded_rows.get("المبيعات", [])) >= 2
    # Verify no 'الإجمالي' remains in data rows
    first_col = df.columns[0]
    assert not df[first_col].astype(str).str.contains("الإجمالي").any()
