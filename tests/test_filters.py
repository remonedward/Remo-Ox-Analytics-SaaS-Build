from __future__ import annotations

"""Unit tests for analytics/filters.py and SafeFilter schema."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from analytics.filters import (
    FilterValidationError,
    apply_filters,
    validate_filters_against_schema,
)
from analytics.schemas import SafeFilter


def test_safe_filter_valid_operators() -> None:
    """SafeFilter accepts valid operators with proper values."""
    f1 = SafeFilter(column="amount", op="gt", value=100)
    assert f1.op == "gt"
    assert f1.value == 100

    f2 = SafeFilter(column="name", op="is_null")
    assert f2.op == "is_null"
    assert f2.value is None

    f3 = SafeFilter(column="status", op="in", value=["active", "pending"])
    assert f3.op == "in"
    assert f3.value == ["active", "pending"]

    f4 = SafeFilter(column="score", op="between", value=[10, 50])
    assert f4.op == "between"
    assert f4.value == [10, 50]


def test_safe_filter_blank_column_and_missing_value() -> None:
    """SafeFilter rejects blank columns and None values for comparison ops."""
    with pytest.raises(ValidationError):
        SafeFilter(column="   ", op="eq", value=1)

    with pytest.raises(ValidationError):
        SafeFilter(column="", op="eq", value=1)

    with pytest.raises(ValidationError):
        SafeFilter(column="amount", op="eq", value=None)

    with pytest.raises(ValidationError):
        SafeFilter(column="amount", op="gt", value=None)


def test_apply_filters_basic(simple_sales_df: pd.DataFrame) -> None:
    """apply_filters correctly subsets DataFrame."""
    filters = [
        SafeFilter(column="category", op="eq", value="Tech"),
        SafeFilter(column="revenue", op="gte", value=500.0),
    ]
    res = apply_filters(simple_sales_df, filters)
    assert len(res) == 5
    assert (res["category"] == "Tech").all()
    assert (res["revenue"] >= 500.0).all()


def test_apply_filters_all_operators() -> None:
    """Test every operator behavior on a toy dataset."""
    df = pd.DataFrame(
        {
            "num": [10, 20, 30, 40, np.nan],
            "text": ["apple", "banana", "cherry", "durian", None],
        }
    )

    # eq
    assert len(apply_filters(df, [SafeFilter(column="num", op="eq", value=20)])) == 1
    # ne: 10, 30, 40, and NaN are != 20 -> 4
    assert len(apply_filters(df, [SafeFilter(column="num", op="ne", value=20)])) == 4
    # gt / gte
    assert len(apply_filters(df, [SafeFilter(column="num", op="gt", value=20)])) == 2
    assert len(apply_filters(df, [SafeFilter(column="num", op="gte", value=20)])) == 3
    # lt / lte
    assert len(apply_filters(df, [SafeFilter(column="num", op="lt", value=20)])) == 1
    assert len(apply_filters(df, [SafeFilter(column="num", op="lte", value=20)])) == 2
    # in
    assert len(apply_filters(df, [SafeFilter(column="text", op="in", value=["apple", "cherry"])])) == 2
    # between
    assert len(apply_filters(df, [SafeFilter(column="num", op="between", value=[15, 35])])) == 2
    # contains
    assert len(apply_filters(df, [SafeFilter(column="text", op="contains", value="an")])) == 2  # banana, durian
    # is_null / not_null
    assert len(apply_filters(df, [SafeFilter(column="num", op="is_null")])) == 1
    assert len(apply_filters(df, [SafeFilter(column="num", op="not_null")])) == 4


def test_apply_filters_unknown_column(simple_sales_df: pd.DataFrame) -> None:
    """Filtering on nonexistent column raises FilterValidationError."""
    with pytest.raises(FilterValidationError):
        apply_filters(simple_sales_df, [SafeFilter(column="nonexistent", op="eq", value=1)])


def test_validate_filters_against_schema() -> None:
    """validate_filters_against_schema reports missing columns."""
    filters = [
        SafeFilter(column="col1", op="eq", value=1),
        SafeFilter(column="col2", op="eq", value=2),
    ]
    errors = validate_filters_against_schema(filters, ["col1", "col3"])
    assert len(errors) == 1
    assert "col2" in errors[0]
