from __future__ import annotations

"""Unit tests for data/mapping.py."""

import pandas as pd

from data.mapping import apply_mapping, auto_map_roles


def test_auto_map_roles_arabic() -> None:
    """auto_map_roles correctly identifies Arabic column synonyms."""
    cols = ["تاريخ البيع", "اسم الصنف", "الكمية", "سعر البيع", "إجمالي الإيرادات", "اسم العميل"]
    res = auto_map_roles(cols)
    mapping = {m.role: m.column for m in res.confirmed}
    assert mapping.get("date") == "تاريخ البيع"
    assert mapping.get("product") == "اسم الصنف"
    assert mapping.get("quantity") == "الكمية"
    assert mapping.get("unit_price") == "سعر البيع"
    assert mapping.get("revenue") == "إجمالي الإيرادات"
    assert mapping.get("customer") == "اسم العميل"


def test_auto_map_roles_english() -> None:
    """auto_map_roles correctly identifies English column roles."""
    cols = ["Transaction Date", "Product SKU", "Qty", "Price", "Total Sales", "Client Name"]
    res = auto_map_roles(cols)
    mapping = {m.role: m.column for m in res.confirmed}
    assert mapping.get("date") == "Transaction Date"
    assert mapping.get("product") == "Product SKU"
    assert mapping.get("quantity") == "Qty"
    assert mapping.get("unit_price") == "Price"
    assert mapping.get("revenue") == "Total Sales"
    assert mapping.get("customer") == "Client Name"


def test_derived_revenue_flag() -> None:
    """Detects derived revenue field when revenue column is absent."""
    cols = ["Date", "Item", "Quantity", "Unit Price"]
    res = auto_map_roles(cols)
    confirmed_roles = {m.role for m in res.confirmed}
    derived_roles = {m.role for m in res.derived}
    assert "revenue" not in confirmed_roles
    assert "revenue" in derived_roles


def test_apply_mapping_computes_derived_revenue() -> None:
    """apply_mapping adds calculated revenue column to DataFrame."""
    df = pd.DataFrame(
        {
            "qty": [2, 5],
            "price": [10.0, 20.0],
        }
    )
    mapping = {"quantity": "qty", "unit_price": "price"}
    mapped_df = apply_mapping(df, mapping)
    assert "_derived_revenue" in mapped_df.columns or "revenue" in mapped_df.columns
