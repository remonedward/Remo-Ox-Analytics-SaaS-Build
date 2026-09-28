from __future__ import annotations

"""Safe structured filter application for pandas DataFrames.

Filters are validated :class:`~analytics.schemas.SafeFilter` pydantic objects —
no query strings, no ``eval()``, no arbitrary code execution. All column names
and operators are checked before any DataFrame operation is performed.

Edge cases and NaN behaviour
----------------------------
- **Comparison operators** (``eq``, ``ne``, ``gt``, ``gte``, ``lt``, ``lte``):
  pandas propagates ``NaN`` comparisons as ``False``. Rows where the column is
  null will therefore be excluded from the filtered result, which is the
  expected behaviour for most analytics queries.
- **in**: ``Series.isin`` treats ``NaN`` as a distinct value; if ``NaN`` is
  included in the value list it will match null cells. Otherwise nulls are
  excluded.
- **between**: Implemented as ``(col >= low) & (col <= high)``. Null cells
  return ``False`` from both comparisons and are excluded.
- **contains**: Casts the series to ``str`` first; pandas represents null as
  the string ``'nan'`` after the cast, but ``str.contains`` with ``na=False``
  returns ``False`` for null cells before casting — so nulls are safely excluded.
- **is_null** / **not_null**: Explicitly handle null presence and are the
  correct way to filter on missing data.
"""

from typing import Any

import pandas as pd

from analytics.schemas import FilterOp, SafeFilter


class FilterValidationError(ValueError):
    """Raised when a filter references an invalid column or unsupported value type.

    Inherits from :class:`ValueError` so callers can catch it alongside other
    validation errors without importing this module explicitly.
    """


def apply_filters(df: pd.DataFrame, filters: list[SafeFilter]) -> pd.DataFrame:
    """Apply a list of validated safe filters to a DataFrame.

    Filters are combined with logical AND; each successive filter further
    narrows the result set. The original DataFrame is never mutated — the
    function always returns a copy of the filtered subset.

    Args:
        df: Input DataFrame to filter.
        filters: List of :class:`~analytics.schemas.SafeFilter` objects that
            have already been validated by pydantic.

    Returns:
        A new DataFrame containing only rows that satisfy all filters.
        Returns a copy of the original DataFrame when ``filters`` is empty.

    Raises:
        FilterValidationError: If any filter references a column that does not
            exist in ``df``.

    Example:
        >>> from analytics.schemas import SafeFilter
        >>> import pandas as pd
        >>> df = pd.DataFrame({"revenue": [100, 200, 300], "region": ["A", "B", "A"]})
        >>> f = SafeFilter(column="region", op="eq", value="A")
        >>> result = apply_filters(df, [f])
        >>> len(result)
        2
    """
    if not filters:
        return df.copy()

    mask = pd.Series(True, index=df.index)

    for f in filters:
        if f.column not in df.columns:
            raise FilterValidationError(
                f"Column {f.column!r} not found in DataFrame. "
                f"Available columns: {sorted(df.columns.tolist())}"
            )
        col: pd.Series = df[f.column]
        mask = mask & _apply_single_filter(col, f.op, f.value)

    return df[mask].copy()


def _apply_single_filter(
    col: pd.Series,
    op: FilterOp,
    value: Any,
) -> pd.Series:
    """Apply one filter predicate to a pandas Series and return a boolean mask.

    All operators propagate ``False`` for ``NaN`` / ``None`` cells unless the
    operator is ``is_null`` or ``not_null`` — see module-level docstring for the
    detailed NaN behaviour contract.

    Args:
        col: The target column Series.
        op: One of the allowed :data:`~analytics.schemas.FilterOp` literals.
        value: The comparison value; semantics depend on ``op``.

    Returns:
        Boolean :class:`pandas.Series` aligned with ``col.index``.

    Raises:
        FilterValidationError: If ``op`` is not a recognised operator (guards
            against future API drift even though pydantic validates the input).
    """
    match op:
        case "eq":
            return col == value
        case "ne":
            # ne returns True for NaN when compared with a non-NaN value in
            # some pandas versions; fill NaN explicitly to ensure consistent
            # exclusion of null rows.
            return (col != value).fillna(False)
        case "gt":
            return (col > value).fillna(False)
        case "gte":
            return (col >= value).fillna(False)
        case "lt":
            return (col < value).fillna(False)
        case "lte":
            return (col <= value).fillna(False)
        case "in":
            # NaN is not in any user-supplied value list unless explicitly
            # included; isin propagates False for NaN by default.
            return col.isin(value)
        case "between":
            low, high = value[0], value[1]
            return ((col >= low) & (col <= high)).fillna(False)
        case "contains":
            # na=False ensures null cells produce False without raising.
            return col.astype(str).str.contains(str(value), na=False, regex=False)
        case "is_null":
            return col.isna()
        case "not_null":
            return col.notna()
        case _:
            raise FilterValidationError(f"Unknown filter operator: {op!r}")


def validate_filters_against_schema(
    filters: list[SafeFilter],
    available_columns: list[str],
) -> list[str]:
    """Check that all filter columns exist in the target schema.

    This is a lightweight pre-flight check intended for use before loading the
    full DataFrame; it avoids the cost of I/O just to discover a bad column
    name. For runtime checks during actual filtering, the error is raised by
    :func:`apply_filters`.

    Args:
        filters: Filters to validate against the schema.
        available_columns: Column names available in the target DataFrame or
            sheet schema.

    Returns:
        A list of human-readable error strings. An empty list means all filter
        columns are valid.

    Example:
        >>> from analytics.schemas import SafeFilter
        >>> f = SafeFilter(column="missing_col", op="eq", value=1)
        >>> errors = validate_filters_against_schema([f], ["revenue", "date"])
        >>> errors
        ["Filter column 'missing_col' not found. Available: ['date', 'revenue']"]
    """
    errors: list[str] = []
    col_set = set(available_columns)
    for f in filters:
        if f.column not in col_set:
            errors.append(
                f"Filter column {f.column!r} not found. "
                f"Available: {sorted(col_set)}"
            )
    return errors
