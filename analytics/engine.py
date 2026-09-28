from __future__ import annotations

"""Deterministic analytics engine for REMO_OX Analytics.

All functions are pure Python / pandas computations.  No LLM calls, no
``eval()``, no arbitrary code execution.  The engine is the single source of
computational truth — the LLM layer only calls these functions via the tool
layer and explains the results to the user.

Public API (module-level functions, each taking ``ctx: DatasetContext`` as
their first argument):

- :func:`get_schema`         — column & quality metadata for all sheets.
- :func:`aggregate`          — group-by + metric aggregation with optional date grain.
- :func:`compare_periods`    — side-by-side metric comparison for two date ranges.
- :func:`top_n`              — top-N rows by a metric with Pareto columns.
- :func:`bottom_n`           — bottom-N rows by a metric.
- :func:`describe_column`    — univariate statistics for any column type.
- :func:`data_quality_report`— flat quality table across all sheets.
- :func:`preview_rows`       — filtered raw row preview.
"""

import json
import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from analytics.filters import FilterValidationError, apply_filters
from analytics.schemas import (
    AggFunc,
    AggregateInput,
    ComparePeriodInput,
    DateGrain,
    DescribeColumnInput,
    MetricSpec,
    PreviewRowsInput,
    QualitySummary,
    SchemaColumn,
    SchemaResult,
    SheetSchema,
    ToolResult,
    TopNInput,
)
from core.logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Hard limits
# ---------------------------------------------------------------------------

_MAX_RESULT_ROWS: int = 50
_MAX_RESULT_CHARS: int = 8_000


# ---------------------------------------------------------------------------
# Engine errors
# ---------------------------------------------------------------------------


class EngineError(Exception):
    """Raised for validated, user-visible engine errors.

    These errors contain actionable messages that are safe to surface directly
    in the UI or in an LLM response.  Internal/unexpected errors should be
    allowed to propagate as plain ``Exception`` or ``RuntimeError``.
    """


# ---------------------------------------------------------------------------
# DatasetContext
# ---------------------------------------------------------------------------


class DatasetContext:
    """Holds the active dataset for one user session.

    Engine functions operate on this context.  Tool arguments from the LLM
    never contain file paths or raw data — the context is bound server-side
    and passed to each function explicitly, keeping the LLM at arm's length
    from the filesystem.

    Attributes:
        sheets: Mapping of sheet_name → cleaned ``pd.DataFrame``.
        mapping: Mapping of role → column_name (confirmed assignments).
        quality_summary: Per-sheet lightweight quality summaries.
        dayfirst: Whether to interpret ambiguous date strings with the day
            first (e.g. ``31/01/2024`` instead of ``01/31/2024``).
        send_sample_rows: When ``True``, :func:`get_schema` includes up to 5
            raw rows and :func:`preview_rows` is permitted.
    """

    def __init__(
        self,
        sheets: dict[str, pd.DataFrame],
        mapping: dict[str, str],
        quality_summary: dict[str, QualitySummary],
        dayfirst: bool = False,
        send_sample_rows: bool = False,
        dataset_id: str | None = None,
    ) -> None:
        """Initialise the context.

        Args:
            sheets: Cleaned DataFrames keyed by sheet name.
            mapping: Confirmed role → column name assignments.
            quality_summary: Lightweight per-sheet quality objects.
            dayfirst: Interpret ambiguous dates day-first.
            send_sample_rows: Allow raw row exposure to the LLM/UI.
            dataset_id: Optional ID of the dataset record.
        """
        self.sheets = sheets
        self.mapping = mapping
        self.quality_summary = quality_summary
        self.dayfirst = dayfirst
        self.send_sample_rows = send_sample_rows
        self.dataset_id = dataset_id
        # Reverse mapping: column_name → role (first-wins on collision)
        self._col_to_role: dict[str, str] = {v: k for k, v in mapping.items()}

    def get_sheet(self, sheet_name: str) -> pd.DataFrame:
        """Return the DataFrame for *sheet_name*, or raise :class:`EngineError`.

        Args:
            sheet_name: Name of the sheet to retrieve.

        Returns:
            The ``pd.DataFrame`` for the requested sheet.

        Raises:
            EngineError: If *sheet_name* is not in :attr:`sheets`.
        """
        if sheet_name not in self.sheets:
            available = list(self.sheets.keys())
            raise EngineError(
                f"Sheet {sheet_name!r} not found. Available sheets: {available}"
            )
        return self.sheets[sheet_name]

    def role_column(self, role: str) -> str | None:
        """Return the column name mapped to *role*, or ``None`` if unmapped.

        Args:
            role: The column role to look up.

        Returns:
            The column name string, or ``None``.
        """
        return self.mapping.get(role)

    def require_role(self, role: str) -> str:
        """Return the column for *role*, or raise :class:`EngineError`.

        Args:
            role: The column role that must be mapped.

        Returns:
            The mapped column name.

        Raises:
            EngineError: If *role* has no confirmed mapping.
        """
        col = self.role_column(role)
        if col is None:
            raise EngineError(
                f"Role {role!r} is not mapped. "
                "Please confirm column mapping before running this analysis."
            )
        return col

    def first_sheet_name(self) -> str:
        """Return the first sheet name in insertion order.

        Returns:
            The first sheet name.

        Raises:
            EngineError: If there are no sheets in context.
        """
        if not self.sheets:
            raise EngineError("No sheets are loaded in the dataset context.")
        return next(iter(self.sheets))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_scalar(value: Any) -> Any:
    """Convert a scalar to a JSON-safe Python primitive.

    Handles ``numpy`` scalars, ``NaN``, ``Inf``, ``NaT``, and Python
    ``datetime``/``date`` objects so the result is always JSON-serialisable.

    Args:
        value: Any scalar value from a pandas computation.

    Returns:
        A JSON-serialisable Python primitive (``None`` for missing/infinite).
    """
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (np.floating,)):
        fv = float(value)
        return None if (math.isnan(fv) or math.isinf(fv)) else fv
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sanitise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *row* with all values made JSON-safe.

    Args:
        row: A dict representing one DataFrame row.

    Returns:
        A new dict with ``_safe_scalar`` applied to every value.
    """
    return {k: _safe_scalar(v) for k, v in row.items()}


def _build_tool_result(
    data_df: pd.DataFrame,
    notes: str | None = None,
    calc_desc: str = "",
    total_rows: int | None = None,
) -> ToolResult:
    """Convert a DataFrame to a :class:`~analytics.schemas.ToolResult`.

    Applies the row cap (:data:`_MAX_RESULT_ROWS`) and character budget
    (:data:`_MAX_RESULT_CHARS`), serialises every value with
    :func:`_safe_scalar`, and sets ``truncated=True`` when the cap fires.

    Args:
        data_df: The result DataFrame to serialise.
        notes: Optional notes or caveats to attach to the result.
        calc_desc: Human-readable explanation of what was computed.
        total_rows: Override the total row count (e.g. after a pre-cap count).
            When ``None``, ``len(data_df)`` is used.

    Returns:
        A fully populated :class:`~analytics.schemas.ToolResult`.
    """
    true_total = total_rows if total_rows is not None else len(data_df)
    truncated = (len(data_df) > _MAX_RESULT_ROWS) or (true_total > len(data_df))

    # Apply row cap
    capped_df = data_df.iloc[: _MAX_RESULT_ROWS]

    # Serialise rows
    rows: list[dict[str, Any]] = [
        _sanitise_row(r) for r in capped_df.to_dict(orient="records")
    ]

    # Apply character budget — drop trailing rows until under budget
    char_count = len(json.dumps(rows, default=str))
    if char_count > _MAX_RESULT_CHARS:
        truncated = True
        while rows and char_count > _MAX_RESULT_CHARS:
            rows.pop()
            char_count = len(json.dumps(rows, default=str))

    return ToolResult(
        data=rows,
        total_rows=true_total,
        truncated=truncated,
        notes=notes,
        calculation_description=calc_desc,
    )


def _apply_date_grain(series: pd.Series, grain: DateGrain) -> pd.Series:
    """Truncate a datetime Series to the requested time grain.

    Returns a string Series suitable for use as a grouping key.  The strings
    are formatted so they sort lexicographically in chronological order.

    Format mapping:

    - ``day``     → ``YYYY-MM-DD``
    - ``week``    → ``YYYY-Www``  (ISO week)
    - ``month``   → ``YYYY-MM``
    - ``quarter`` → ``YYYY-Qn``
    - ``year``    → ``YYYY``

    Args:
        series: A pandas Series with a datetime-like dtype.
        grain: One of the :data:`~analytics.schemas.DateGrain` literals.

    Returns:
        A ``pd.Series`` of ``str`` (or ``None`` for NaT values).

    Raises:
        EngineError: If *grain* is not a recognised value (guards against
            future API drift).
    """
    dt = pd.to_datetime(series, errors="coerce")
    match grain:
        case "day":
            return dt.dt.strftime("%Y-%m-%d")
        case "week":
            # ISO week: zero-pad week number so it sorts correctly
            return dt.dt.strftime("%G-W%V")
        case "month":
            return dt.dt.strftime("%Y-%m")
        case "quarter":
            return dt.dt.to_period("Q").astype(str)
        case "year":
            return dt.dt.strftime("%Y")
        case _:  # pragma: no cover
            raise EngineError(f"Unknown date grain: {grain!r}")


def _compute_agg(
    group: pd.core.groupby.DataFrameGroupBy,
    col: str,
    agg: AggFunc,
) -> pd.Series:
    """Apply an aggregation function to *col* within a GroupBy object.

    Args:
        group: A pandas ``DataFrameGroupBy`` targeting the result DataFrame.
        col: The column to aggregate.
        agg: One of the allowed :data:`~analytics.schemas.AggFunc` literals.

    Returns:
        An aggregated ``pd.Series`` indexed by the group keys.

    Raises:
        EngineError: If *agg* is not a recognised aggregation function.
    """
    match agg:
        case "sum":
            return group[col].sum()
        case "mean":
            return group[col].mean()
        case "median":
            return group[col].median()
        case "count":
            return group[col].count()
        case "nunique":
            return group[col].nunique()
        case "min":
            return group[col].min()
        case "max":
            return group[col].max()
        case _:  # pragma: no cover
            raise EngineError(f"Unknown aggregation function: {agg!r}")


def _metric_alias(m: MetricSpec) -> str:
    """Return the output column name for a metric.

    Uses ``m.alias`` when set; otherwise constructs ``"{column}_{agg}"``.

    Args:
        m: The metric specification.

    Returns:
        The output column name string.
    """
    return m.alias if m.alias else f"{m.column}_{m.agg}"


def _scalar_agg(series: pd.Series, agg: AggFunc) -> Any:
    """Compute a scalar aggregate on a plain Series (no groupby).

    Args:
        series: The data Series to aggregate.
        agg: One of the allowed :data:`~analytics.schemas.AggFunc` literals.

    Returns:
        A scalar result.

    Raises:
        EngineError: If *agg* is not a recognised aggregation function.
    """
    match agg:
        case "sum":
            return series.sum()
        case "mean":
            return series.mean()
        case "median":
            return series.median()
        case "count":
            return series.count()
        case "nunique":
            return series.nunique()
        case "min":
            return series.min()
        case "max":
            return series.max()
        case _:  # pragma: no cover
            raise EngineError(f"Unknown aggregation function: {agg!r}")


# ---------------------------------------------------------------------------
# Public engine functions
# ---------------------------------------------------------------------------


def get_schema(ctx: DatasetContext) -> SchemaResult:
    """Return schema and quality metadata for all sheets in context.

    Iterates over every sheet in ``ctx.sheets``, extracts per-column metadata
    (dtype, mapped role, null percentage, sample values), and attaches the
    lightweight quality summary.  Raw sample rows are included only when
    ``ctx.send_sample_rows`` is ``True``.

    Args:
        ctx: The active :class:`DatasetContext`.

    Returns:
        A :class:`~analytics.schemas.SchemaResult` covering all sheets.
    """
    sheet_schemas: list[SheetSchema] = []

    for sheet_name, df in ctx.sheets.items():
        columns: list[SchemaColumn] = []
        for col in df.columns:
            mapped_role = ctx._col_to_role.get(col)
            null_pct = float(df[col].isna().mean() * 100)
            # Sample up to 3 non-null values
            non_null = df[col].dropna()
            sample_vals = [str(v) for v in non_null.head(3).tolist()]

            columns.append(
                SchemaColumn(
                    name=col,
                    dtype=str(df[col].dtype),
                    mapped_role=mapped_role,
                    null_pct=round(null_pct, 2),
                    sample_values=sample_vals,
                )
            )

        sample_rows: list[dict[str, Any]] = []
        if ctx.send_sample_rows:
            sample_rows = [
                _sanitise_row(r) for r in df.head(5).to_dict(orient="records")
            ]

        sheet_schemas.append(
            SheetSchema(
                sheet_name=sheet_name,
                row_count=len(df),
                columns=columns,
                sample_rows=sample_rows,
            )
        )

    return SchemaResult(
        sheets=sheet_schemas,
        quality=ctx.quality_summary,
        mapped_roles=ctx.mapping,
    )


def aggregate(ctx: DatasetContext, inp: AggregateInput) -> ToolResult:
    """Group and aggregate one sheet according to *inp*.

    Applies optional filters, optional date-grain bucketing on a date column,
    groups by the specified columns (plus the bucketed date column), and
    computes each metric.  Sorting and row limits are applied after
    aggregation.  When ``inp.group_by`` is empty (and no date column is given),
    a single-row grand total is returned.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated aggregation parameters.

    Returns:
        A :class:`~analytics.schemas.ToolResult` containing the aggregated rows.
    """
    try:
        df = ctx.get_sheet(inp.sheet_name).copy()
    except EngineError as exc:
        return ToolResult(error=str(exc))

    # ── Validate metric columns exist ────────────────────────────────────────
    for m in inp.metrics:
        if m.column not in df.columns:
            return ToolResult(
                error=(
                    f"Metric column {m.column!r} not found in sheet "
                    f"{inp.sheet_name!r}. Available: {sorted(df.columns.tolist())}"
                )
            )

    # ── Apply filters ────────────────────────────────────────────────────────
    if inp.filters:
        try:
            df = apply_filters(df, inp.filters)
        except FilterValidationError as exc:
            return ToolResult(error=str(exc))

    if df.empty:
        return ToolResult(
            data=[],
            total_rows=0,
            calculation_description="No rows remain after applying filters.",
        )

    # ── Date grain bucketing ─────────────────────────────────────────────────
    grain_col: str | None = None
    if inp.date_column and inp.date_grain:
        if inp.date_column not in df.columns:
            return ToolResult(
                error=(
                    f"date_column {inp.date_column!r} not found in sheet "
                    f"{inp.sheet_name!r}."
                )
            )
        grain_col = f"__{inp.date_grain}__"
        df[grain_col] = _apply_date_grain(df[inp.date_column], inp.date_grain)

    # ── Build group key list ─────────────────────────────────────────────────
    group_keys: list[str] = []
    if grain_col:
        group_keys.append(grain_col)
    group_keys.extend(inp.group_by)

    # ── Aggregate ────────────────────────────────────────────────────────────
    if not group_keys:
        # Grand total — single-row result
        row: dict[str, Any] = {}
        for m in inp.metrics:
            alias = _metric_alias(m)
            row[alias] = _safe_scalar(_scalar_agg(df[m.column], m.agg))
        result_df = pd.DataFrame([row])
    else:
        # Validate group_by columns exist
        missing_gb = [c for c in inp.group_by if c not in df.columns]
        if missing_gb:
            return ToolResult(
                error=(
                    f"group_by column(s) {missing_gb} not found in sheet "
                    f"{inp.sheet_name!r}."
                )
            )

        group = df.groupby(group_keys, sort=False, observed=True)
        agg_parts: dict[str, pd.Series] = {}
        for m in inp.metrics:
            alias = _metric_alias(m)
            agg_parts[alias] = _compute_agg(group, m.column, m.agg)

        result_df = pd.DataFrame(agg_parts).reset_index()

        # Rename internal grain column back to readable label
        if grain_col and grain_col in result_df.columns:
            result_df = result_df.rename(
                columns={grain_col: inp.date_grain or grain_col}
            )

    # ── Sort ─────────────────────────────────────────────────────────────────
    if inp.sort_by and inp.sort_by in result_df.columns:
        result_df = result_df.sort_values(
            inp.sort_by, ascending=not inp.sort_desc
        )
    elif group_keys and not inp.sort_by:
        # Default: sort by first metric descending
        first_alias = _metric_alias(inp.metrics[0])
        if first_alias in result_df.columns:
            result_df = result_df.sort_values(
                first_alias, ascending=not inp.sort_desc
            )

    # ── Limit ────────────────────────────────────────────────────────────────
    total_rows = len(result_df)
    result_df = result_df.iloc[: inp.limit]

    # ── Build description ────────────────────────────────────────────────────
    metric_strs = [
        f"{m.agg.upper()}({m.column}) as {_metric_alias(m)}" for m in inp.metrics
    ]
    group_str = ", ".join(group_keys) if group_keys else "grand total"
    filter_str = (
        f" with {len(inp.filters)} filter(s) applied" if inp.filters else ""
    )
    date_str = (
        f" bucketed to {inp.date_grain} grain on '{inp.date_column}'"
        if grain_col
        else ""
    )
    calc_desc = (
        f"Computed {'; '.join(metric_strs)} "
        f"grouped by [{group_str}]{date_str}{filter_str} "
        f"from sheet '{inp.sheet_name}' "
        f"({total_rows:,} result row{'s' if total_rows != 1 else ''})."
    )

    return _build_tool_result(
        result_df,
        calc_desc=calc_desc,
        total_rows=total_rows,
    )


def compare_periods(ctx: DatasetContext, inp: ComparePeriodInput) -> ToolResult:
    """Compare a metric between two date periods, optionally per-segment.

    Filters the sheet to each period separately, computes the metric aggregate
    for each, then joins the results to produce a side-by-side comparison with
    absolute change and percentage change columns.

    When ``inp.group_by`` is non-empty the comparison is performed per group.
    When ``inp.group_by`` is empty a single summary row is returned.

    Divide-by-zero for percentage change (period_a value = 0) is handled
    gracefully — the result cell is ``None``.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated period-comparison parameters.

    Returns:
        A :class:`~analytics.schemas.ToolResult` with comparison columns.
    """
    try:
        df = ctx.get_sheet(inp.sheet_name).copy()
    except EngineError as exc:
        return ToolResult(error=str(exc))

    # Apply global pre-filters first
    if inp.filters:
        try:
            df = apply_filters(df, inp.filters)
        except FilterValidationError as exc:
            return ToolResult(error=str(exc))

    metric_col = inp.metric.column
    if metric_col not in df.columns:
        return ToolResult(
            error=(
                f"Metric column {metric_col!r} not found in sheet "
                f"{inp.sheet_name!r}."
            )
        )

    alias = _metric_alias(inp.metric)

    def _period_df(spec: analytics.schemas.PeriodSpec) -> pd.DataFrame:  # noqa: F821
        """Filter *df* to the given period and aggregate."""
        date_col = spec.date_column
        if date_col not in df.columns:
            raise EngineError(
                f"date_column {date_col!r} not found in sheet {inp.sheet_name!r}."
            )
        dates = pd.to_datetime(df[date_col], errors="coerce")
        mask = (dates >= spec.start) & (dates <= spec.end)
        sliced = df[mask]

        if inp.group_by:
            missing = [c for c in inp.group_by if c not in sliced.columns]
            if missing:
                raise EngineError(
                    f"group_by column(s) {missing} not found in sheet "
                    f"{inp.sheet_name!r}."
                )
            group = sliced.groupby(inp.group_by, sort=False, observed=True)
            result = _compute_agg(group, metric_col, inp.metric.agg).reset_index()
            result = result.rename(columns={metric_col: alias})
        else:
            value = _scalar_agg(sliced[metric_col], inp.metric.agg)
            result = pd.DataFrame([{alias: _safe_scalar(value)}])

        return result

    try:
        df_a = _period_df(inp.period_a)
        df_b = _period_df(inp.period_b)
    except EngineError as exc:
        return ToolResult(error=str(exc))

    col_a = f"{alias}_period_a"
    col_b = f"{alias}_period_b"

    if inp.group_by:
        # Rename metric columns before merge
        df_a = df_a.rename(columns={alias: col_a})
        df_b = df_b.rename(columns={alias: col_b})
        result_df = pd.merge(df_a, df_b, on=inp.group_by, how="outer")
    else:
        val_a = df_a[alias].iloc[0] if not df_a.empty else None
        val_b = df_b[alias].iloc[0] if not df_b.empty else None
        result_df = pd.DataFrame([{col_a: val_a, col_b: val_b}])

    # Absolute change
    result_df["abs_change"] = result_df[col_b] - result_df[col_a]

    # Percentage change (safe division)
    def _pct(b: Any, a: Any) -> float | None:
        try:
            a_f, b_f = float(a), float(b)
        except (TypeError, ValueError):
            return None
        if a_f == 0:
            return None
        return round((b_f - a_f) / abs(a_f) * 100, 2)

    result_df["pct_change"] = result_df.apply(
        lambda row: _pct(row[col_b], row[col_a]), axis=1
    )

    calc_desc = (
        f"Compared {inp.metric.agg.upper()}({metric_col}) "
        f"between period A [{inp.period_a.start} → {inp.period_a.end}] "
        f"and period B [{inp.period_b.start} → {inp.period_b.end}] "
        f"from sheet '{inp.sheet_name}'"
        + (f" grouped by {inp.group_by}." if inp.group_by else ".")
    )

    return _build_tool_result(
        result_df,
        calc_desc=calc_desc,
        total_rows=len(result_df),
    )


def top_n(ctx: DatasetContext, inp: TopNInput) -> ToolResult:
    """Return the top-N rows ranked by a metric with Pareto share columns.

    Aggregates the metric by ``inp.category_column``, sorts descending by the
    metric value, adds a ``share_of_total`` column (value ÷ grand total × 100)
    and a ``cumulative_share`` running total, then returns the first *n* rows.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated top-N parameters (``inp.descending=True``).

    Returns:
        A :class:`~analytics.schemas.ToolResult` with the top rows.
    """
    return _rank_n(ctx, inp, descending=True)


def bottom_n(ctx: DatasetContext, inp: TopNInput) -> ToolResult:
    """Return the bottom-N rows ranked by a metric with share columns.

    Identical to :func:`top_n` but sorts ascending so the lowest-value items
    appear first.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated top-N parameters (``inp.descending=False``).

    Returns:
        A :class:`~analytics.schemas.ToolResult` with the bottom rows.
    """
    return _rank_n(ctx, inp, descending=False)


def _rank_n(
    ctx: DatasetContext, inp: TopNInput, descending: bool
) -> ToolResult:
    """Internal implementation shared by :func:`top_n` and :func:`bottom_n`.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated top-N parameters.
        descending: ``True`` for top-N, ``False`` for bottom-N.

    Returns:
        A :class:`~analytics.schemas.ToolResult`.
    """
    try:
        df = ctx.get_sheet(inp.sheet_name).copy()
    except EngineError as exc:
        return ToolResult(error=str(exc))

    if inp.category_column not in df.columns:
        return ToolResult(
            error=(
                f"category_column {inp.category_column!r} not found in sheet "
                f"{inp.sheet_name!r}."
            )
        )
    if inp.metric.column not in df.columns:
        return ToolResult(
            error=(
                f"Metric column {inp.metric.column!r} not found in sheet "
                f"{inp.sheet_name!r}."
            )
        )

    if inp.filters:
        try:
            df = apply_filters(df, inp.filters)
        except FilterValidationError as exc:
            return ToolResult(error=str(exc))

    if df.empty:
        return ToolResult(
            data=[],
            total_rows=0,
            calculation_description="No rows remain after applying filters.",
        )

    alias = _metric_alias(inp.metric)
    group = df.groupby(inp.category_column, sort=False, observed=True)
    aggregated = (
        _compute_agg(group, inp.metric.column, inp.metric.agg)
        .reset_index()
        .rename(columns={inp.metric.column: alias})
    )

    # Sort
    aggregated = aggregated.sort_values(alias, ascending=not descending)

    # Grand total for share calculation (uses full aggregated set, not sliced)
    grand_total = aggregated[alias].sum()

    # Slice to n
    sliced = aggregated.iloc[: inp.n].copy()

    # Share and cumulative share
    if grand_total != 0:
        sliced["share_of_total"] = (sliced[alias] / grand_total * 100).round(2)
    else:
        sliced["share_of_total"] = 0.0
    sliced["cumulative_share"] = sliced["share_of_total"].cumsum().round(2)

    direction = "top" if descending else "bottom"
    calc_desc = (
        f"{direction.capitalize()}-{inp.n} {inp.category_column} by "
        f"{inp.metric.agg.upper()}({inp.metric.column}) "
        f"from sheet '{inp.sheet_name}'. "
        f"share_of_total and cumulative_share are computed against all "
        f"{len(aggregated):,} distinct {inp.category_column} values "
        f"(grand total = {_safe_scalar(grand_total):,})."
    )

    return _build_tool_result(
        sliced,
        calc_desc=calc_desc,
        total_rows=len(sliced),
    )


def describe_column(ctx: DatasetContext, inp: DescribeColumnInput) -> ToolResult:
    """Compute univariate statistics for a single column.

    The statistics returned depend on the column's inferred type:

    - **Numeric**: count, null_count, mean, median, std, min, p25, p75, max,
      negative_count, zero_count.
    - **Categorical (object/string)**: count, null_count, unique_count,
      top-5 value frequencies.
    - **Datetime**: count, null_count, min, max, date_range_days.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated describe parameters.

    Returns:
        A :class:`~analytics.schemas.ToolResult` whose ``data`` contains
        key-value dicts (one dict per statistic row).
    """
    try:
        df = ctx.get_sheet(inp.sheet_name).copy()
    except EngineError as exc:
        return ToolResult(error=str(exc))

    if inp.column not in df.columns:
        return ToolResult(
            error=(
                f"Column {inp.column!r} not found in sheet {inp.sheet_name!r}. "
                f"Available: {sorted(df.columns.tolist())}"
            )
        )

    if inp.filters:
        try:
            df = apply_filters(df, inp.filters)
        except FilterValidationError as exc:
            return ToolResult(error=str(exc))

    series = df[inp.column]
    dtype = series.dtype
    records: list[dict[str, Any]] = []

    common_null_count = int(series.isna().sum())
    common_count = int(series.notna().sum())

    if pd.api.types.is_numeric_dtype(dtype):
        non_null = series.dropna()
        records = [
            {"statistic": "count", "value": common_count},
            {"statistic": "null_count", "value": common_null_count},
            {"statistic": "mean", "value": _safe_scalar(non_null.mean())},
            {"statistic": "median", "value": _safe_scalar(non_null.median())},
            {"statistic": "std", "value": _safe_scalar(non_null.std())},
            {"statistic": "min", "value": _safe_scalar(non_null.min())},
            {"statistic": "p25", "value": _safe_scalar(non_null.quantile(0.25))},
            {"statistic": "p75", "value": _safe_scalar(non_null.quantile(0.75))},
            {"statistic": "max", "value": _safe_scalar(non_null.max())},
            {"statistic": "negative_count", "value": int((non_null < 0).sum())},
            {"statistic": "zero_count", "value": int((non_null == 0).sum())},
        ]
        calc_desc = (
            f"Numeric univariate statistics for column '{inp.column}' "
            f"in sheet '{inp.sheet_name}' ({common_count:,} non-null values)."
        )

    elif pd.api.types.is_datetime64_any_dtype(dtype):
        non_null = series.dropna()
        min_val = non_null.min() if not non_null.empty else None
        max_val = non_null.max() if not non_null.empty else None
        date_range_days: int | None = None
        if min_val is not None and max_val is not None:
            date_range_days = int((max_val - min_val).days)
        records = [
            {"statistic": "count", "value": common_count},
            {"statistic": "null_count", "value": common_null_count},
            {
                "statistic": "min",
                "value": min_val.isoformat() if min_val is not None else None,
            },
            {
                "statistic": "max",
                "value": max_val.isoformat() if max_val is not None else None,
            },
            {"statistic": "date_range_days", "value": date_range_days},
        ]
        calc_desc = (
            f"Datetime statistics for column '{inp.column}' "
            f"in sheet '{inp.sheet_name}' ({common_count:,} non-null values)."
        )

    else:
        # Categorical / object
        unique_count = int(series.nunique())
        top5 = series.value_counts().head(5)
        records = [
            {"statistic": "count", "value": common_count},
            {"statistic": "null_count", "value": common_null_count},
            {"statistic": "unique_count", "value": unique_count},
        ]
        for rank, (val, freq) in enumerate(top5.items(), start=1):
            records.append(
                {
                    "statistic": f"top_{rank}_value",
                    "value": str(val),
                    "frequency": int(freq),
                }
            )
        calc_desc = (
            f"Categorical statistics for column '{inp.column}' "
            f"in sheet '{inp.sheet_name}' "
            f"({unique_count:,} unique values, {common_count:,} non-null)."
        )

    result_df = pd.DataFrame(records)
    return _build_tool_result(
        result_df,
        calc_desc=calc_desc,
        total_rows=len(result_df),
    )


def data_quality_report(ctx: DatasetContext) -> ToolResult:
    """Return a flat quality table covering all sheets in context.

    Assembles the lightweight :class:`~analytics.schemas.QualitySummary`
    objects from ``ctx.quality_summary`` into a single, sortable DataFrame.
    Columns: ``sheet``, ``column``, ``null_pct``, ``outlier_count``,
    ``parse_failures``.  Rows are sorted by ``null_pct`` descending so the
    most problematic columns appear first.

    Args:
        ctx: The active :class:`DatasetContext`.

    Returns:
        A :class:`~analytics.schemas.ToolResult` with one row per
        sheet×column combination.
    """
    rows: list[dict[str, Any]] = []

    for sheet_name, qs in ctx.quality_summary.items():
        # Determine all columns from the DataFrame
        df = ctx.sheets.get(sheet_name)
        columns = list(df.columns) if df is not None else list(qs.null_pct_by_column.keys())

        for col in columns:
            rows.append(
                {
                    "sheet": sheet_name,
                    "column": col,
                    "null_pct": qs.null_pct_by_column.get(col, 0.0),
                    "outlier_count": qs.outlier_count_by_column.get(col, 0),
                    "parse_failures": qs.parse_failure_by_column.get(col, 0),
                    "mapped_role": ctx._col_to_role.get(col),
                }
            )

    if not rows:
        return ToolResult(
            data=[],
            total_rows=0,
            calculation_description="No quality summary data available.",
        )

    result_df = pd.DataFrame(rows).sort_values("null_pct", ascending=False)
    calc_desc = (
        f"Data quality report across {len(ctx.quality_summary)} sheet(s). "
        f"Rows are sorted by null_pct descending. "
        f"Total columns reviewed: {len(rows):,}."
    )
    return _build_tool_result(
        result_df,
        calc_desc=calc_desc,
        total_rows=len(result_df),
    )


def preview_rows(ctx: DatasetContext, inp: PreviewRowsInput) -> ToolResult:
    """Return up to *limit* raw rows after applying optional filters.

    This function should only be called when ``ctx.send_sample_rows`` is
    ``True``; the tool layer is responsible for enforcing that gate.

    Args:
        ctx: The active :class:`DatasetContext`.
        inp: Validated preview parameters.

    Returns:
        A :class:`~analytics.schemas.ToolResult` with the raw rows.
    """
    if not ctx.send_sample_rows:
        return ToolResult(error="Previewing raw rows is disabled by privacy configuration.")

    try:
        df = ctx.get_sheet(inp.sheet_name).copy()
    except EngineError as exc:
        return ToolResult(error=str(exc))

    if inp.filters:
        try:
            df = apply_filters(df, inp.filters)
        except FilterValidationError as exc:
            return ToolResult(error=str(exc))

    total_rows = len(df)
    preview = df.head(inp.limit)

    filter_str = (
        f" after applying {len(inp.filters)} filter(s)" if inp.filters else ""
    )
    calc_desc = (
        f"Preview of {len(preview):,} row(s) from sheet '{inp.sheet_name}'"
        f"{filter_str} ({total_rows:,} rows total in filtered set)."
    )

    return _build_tool_result(
        preview,
        calc_desc=calc_desc,
        total_rows=total_rows,
    )
