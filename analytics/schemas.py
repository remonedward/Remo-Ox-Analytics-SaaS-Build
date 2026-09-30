from __future__ import annotations

"""Shared Pydantic v2 data models for REMO_OX Analytics.

These schemas are the single source of truth for structured data exchanged
between the ingestion, mapping, quality, engine, and LLM modules.

Notes on SafeFilter.op
----------------------
The ``op`` field uses the :data:`FilterOp` literal alias set.  The companion
``analytics.filters`` module imports ``FilterOp`` and accesses ``f.op`` —
any change to the field name here must be reflected there.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Column role type
# ---------------------------------------------------------------------------

ColumnRole = Literal[
    "date",
    "product",
    "category",
    "customer",
    "quantity",
    "unit_price",
    "revenue",
    "unit_cost",
    "cost",
    "expense_amount",
    "stock_qty",
    "last_movement_date",
    "invoice_amount",
    "paid_amount",
    "due_date",
    "invoice_date",
]

ALL_ROLES: list[str] = list(ColumnRole.__args__)  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Filter primitives
# ---------------------------------------------------------------------------

FilterOp = Literal[
    "eq", "ne", "gt", "gte", "lt", "lte",
    "in", "between", "contains", "is_null", "not_null",
]
"""All allowed filter operators consumed by :mod:`analytics.filters`."""


class SafeFilter(BaseModel):
    """A validated, serialisable filter clause for dataset queries.

    Attributes:
        column: Column name to filter on.
        op: Comparison operator (see :data:`FilterOp`).
        value: Filter value — scalar for scalar operators, two-element list for
            ``between``, list of scalars for ``in``.  ``None`` for ``is_null``
            and ``not_null`` operators which need no value.
    """

    column: str = Field(..., min_length=1)
    op: FilterOp
    value: str | int | float | list[str | int | float] | None = None

    @field_validator("column")
    @classmethod
    def column_not_blank(cls, v: str) -> str:
        """Ensure column name is non-blank after stripping whitespace."""
        if not v.strip():
            raise ValueError("column must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def value_required_for_value_ops(self) -> SafeFilter:
        """Ensure a value is supplied for every operator that compares values."""
        null_ops: frozenset[str] = frozenset({"is_null", "not_null"})
        if self.op not in null_ops and self.value is None:
            raise ValueError(f"op={self.op!r} requires a non-None value")
        return self


# ---------------------------------------------------------------------------
# Mapping models
# ---------------------------------------------------------------------------


class MappingSuggestion(BaseModel):
    """A candidate role assignment for a single column.

    Attributes:
        role: The suggested ColumnRole.
        confidence: Similarity score in [0, 1].
        source: How the suggestion was produced ('fuzzy', 'llm', 'derived').
    """

    role: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: Literal["fuzzy", "llm", "derived"] = "fuzzy"


class DatasetMapping(BaseModel):
    """Confirmed role assignment for a single column.

    Attributes:
        column: Actual column name in the DataFrame.
        role: Assigned ColumnRole.
        is_derived: Whether this column is computed rather than raw.
        derived_from: Source column names if is_derived is True.
    """

    column: str
    role: str
    is_derived: bool = False
    derived_from: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def derived_must_have_sources(self) -> DatasetMapping:
        """Validate that derived columns specify their sources."""
        if self.is_derived and not self.derived_from:
            raise ValueError(
                "derived columns must list their source columns in derived_from"
            )
        return self


class MappingResult(BaseModel):
    """Full mapping result for one sheet.

    Attributes:
        confirmed: Columns assigned with confidence >= threshold.
        suggestions: Columns with candidate roles below auto-assign threshold.
        unresolved: Column names that could not be matched to any role.
        derived: Roles that will be computed from existing mapped columns.
    """

    confirmed: list[DatasetMapping] = Field(default_factory=list)
    suggestions: dict[str, list[MappingSuggestion]] = Field(default_factory=dict)
    unresolved: list[str] = Field(default_factory=list)
    derived: list[DatasetMapping] = Field(default_factory=list)

    @property
    def mapping(self) -> dict[str, str]:
        """Return role -> column dictionary for all confirmed mappings."""
        return {m.role: m.column for m in self.confirmed}


# ---------------------------------------------------------------------------
# Quality models
# ---------------------------------------------------------------------------


class ColumnQualityReport(BaseModel):
    """Quality statistics for a single DataFrame column.

    Attributes:
        column: Column name.
        role: Mapped role (if any).
        null_count: Number of null/NaN values.
        null_pct: Percentage of null values in [0, 100].
        parse_failures: Values that should be numeric/date but failed parsing.
        outliers_count: Number of IQR-based outliers (numeric columns only).
        negative_count: Number of negative values (suspicious for qty/price).
        unique_count: Number of distinct non-null values.
        sample_issues: Up to 3 example problematic cell values (as strings).
    """

    column: str
    role: str | None = None
    null_count: int = 0
    null_pct: float = Field(0.0, ge=0.0, le=100.0)
    parse_failures: int = 0
    outliers_count: int = 0
    negative_count: int = 0
    unique_count: int = 0
    sample_issues: list[str] = Field(default_factory=list)


class SheetQualityReport(BaseModel):
    """Quality report for one Excel sheet.

    Attributes:
        sheet_name: Name of the sheet.
        row_count: Total data rows (after header detection, before exclusions).
        duplicate_rows: Number of fully duplicated rows.
        excluded_total_rows: Number of total/summary rows that were excluded.
        columns: Per-column quality statistics.
        warnings: Human-readable warning messages for significant issues.
    """

    sheet_name: str
    row_count: int = 0
    duplicate_rows: int = 0
    excluded_total_rows: int = 0
    columns: list[ColumnQualityReport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    """Top-level quality report spanning all uploaded sheets.

    Attributes:
        sheets: Quality details per sheet.
        overall_warnings: Warnings that apply across all sheets.
    """

    sheets: list[SheetQualityReport] = Field(default_factory=list)
    overall_warnings: list[str] = Field(default_factory=list)

    def to_summary(self, sheet_name: str) -> QualitySummary:
        """Convert sheet quality report to a lightweight QualitySummary."""
        for s in self.sheets:
            if s.sheet_name == sheet_name:
                return QualitySummary(
                    sheet_name=sheet_name,
                    row_count=s.row_count,
                    null_pct_by_column={c.column: c.null_pct for c in s.columns},
                    outlier_count_by_column={c.column: c.outliers_count for c in s.columns},
                    parse_failure_by_column={c.column: c.parse_failures for c in s.columns},
                    warnings=s.warnings,
                )
        return QualitySummary(sheet_name=sheet_name)


# ---------------------------------------------------------------------------
# QualitySummary — lightweight summary stored on DatasetContext
# ---------------------------------------------------------------------------


class QualitySummary(BaseModel):
    """Lightweight per-sheet quality summary stored in :class:`~analytics.engine.DatasetContext`.

    Attributes:
        sheet_name: Name of the sheet.
        row_count: Number of data rows.
        null_pct_by_column: Mapping of column name to null percentage (0-100).
        outlier_count_by_column: Mapping of column name to IQR-outlier count.
        parse_failure_by_column: Mapping of column name to parse failure count.
        warnings: Human-readable quality warnings.
    """

    sheet_name: str
    row_count: int = 0
    null_pct_by_column: dict[str, float] = Field(default_factory=dict)
    outlier_count_by_column: dict[str, int] = Field(default_factory=dict)
    parse_failure_by_column: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine tool result models
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Result returned by every engine analytics function.

    Attributes:
        data: List of row dicts (JSON-serialisable). Capped at 50 rows.
        total_rows: True row count before the cap was applied.
        truncated: True when ``total_rows > len(data)``.
        notes: Optional free-text notes or caveats about the result.
        calculation_description: Human-readable explanation of what was computed.
        error: Non-None when computation failed; ``data`` will be empty.
    """

    data: list[dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    truncated: bool = False
    notes: str | None = None
    calculation_description: str = ""
    error: str | None = None

    @property
    def columns(self) -> list[str]:
        """Return list of column names inferred from data records."""
        if self.data:
            return list(self.data[0].keys())
        return []


# ---------------------------------------------------------------------------
# Schema result models
# ---------------------------------------------------------------------------


class SchemaColumn(BaseModel):
    """Metadata for a single column returned by :func:`~analytics.engine.get_schema`.

    Attributes:
        name: Column name.
        dtype: Pandas dtype string (e.g. 'float64', 'object', 'datetime64[ns]').
        mapped_role: Role assigned to this column, or None.
        null_pct: Percentage of null values (0–100).
        sample_values: Up to 3 representative non-null values (as strings).
    """

    name: str
    dtype: str
    mapped_role: str | None = None
    null_pct: float = 0.0
    sample_values: list[str] = Field(default_factory=list)


class SheetSchema(BaseModel):
    """Schema information for one sheet.

    Attributes:
        sheet_name: Name of the sheet.
        row_count: Number of data rows.
        columns: Per-column metadata list.
        sample_rows: Up to 5 raw data rows (only populated when enabled in ctx).
    """

    sheet_name: str
    row_count: int = 0
    columns: list[SchemaColumn] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class SchemaResult(BaseModel):
    """Full schema inspection result returned by :func:`~analytics.engine.get_schema`.

    Attributes:
        sheets: Per-sheet schema info.
        quality: Per-sheet quality summary keyed by sheet name.
        mapped_roles: Current role -> column mapping (from DatasetContext).
    """

    sheets: list[SheetSchema] = Field(default_factory=list)
    quality: dict[str, QualitySummary] = Field(default_factory=dict)
    mapped_roles: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregation / engine input models
# ---------------------------------------------------------------------------

AggFunc = Literal["sum", "mean", "median", "count", "nunique", "min", "max"]
"""Allowed aggregation functions for engine computations."""

DateGrain = Literal["day", "week", "month", "quarter", "year"]
"""Time granularities for date-based grouping in :func:`~analytics.engine.aggregate`."""


class MetricSpec(BaseModel):
    """Specification for a single metric to compute during aggregation.

    Attributes:
        column: Column name to aggregate.
        agg: Aggregation function to apply.
        alias: Optional output column name override; defaults to
            ``"{column}_{agg}"`` when not supplied.
    """

    column: str = Field(..., min_length=1)
    agg: AggFunc = "sum"
    alias: str | None = None

    @field_validator("column")
    @classmethod
    def column_not_blank(cls, v: str) -> str:
        """Ensure column name is non-blank after stripping whitespace."""
        if not v.strip():
            raise ValueError("column must not be blank")
        return v.strip()


class PeriodSpec(BaseModel):
    """Date range specification for period-comparison queries.

    Attributes:
        date_column: Column containing the dates to filter on.
        start: Inclusive start date in YYYY-MM-DD format.
        end: Inclusive end date in YYYY-MM-DD format.
    """

    date_column: str = Field(..., min_length=1)
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def start_before_end(self) -> PeriodSpec:
        """Ensure start date is not after end date."""
        if self.start > self.end:
            raise ValueError(
                f"start {self.start!r} must be <= end {self.end!r}"
            )
        return self


class AggregateInput(BaseModel):
    """Input model for :func:`~analytics.engine.aggregate`.

    Attributes:
        sheet_name: Target sheet to query.
        metrics: One or more metric specifications to compute.
        group_by: Columns to group by (empty list = single-row grand total).
        filters: Optional filter clauses applied before aggregation.
        date_column: Column to apply date_grain bucketing to (if given).
        date_grain: Time granularity for date_column bucketing.
        sort_by: Output column name to sort by after aggregation.
        sort_desc: Sort descending when True (default).
        limit: Maximum number of result rows (applied after sort).
    """

    sheet_name: str = Field(..., min_length=1)
    metrics: list[MetricSpec] = Field(..., min_length=1)
    group_by: list[str] = Field(default_factory=list)
    filters: list[SafeFilter] = Field(default_factory=list)
    date_column: str | None = None
    date_grain: DateGrain | None = None
    sort_by: str | None = None
    sort_desc: bool = True
    limit: int = Field(50, ge=1, le=500)


class ComparePeriodInput(BaseModel):
    """Input model for :func:`~analytics.engine.compare_periods`.

    Attributes:
        sheet_name: Target sheet to query.
        metric: The metric to compare across the two periods.
        period_a: First (baseline) period definition.
        period_b: Second (comparison) period definition.
        group_by: Optional grouping columns for per-segment comparison.
        filters: Optional pre-filter applied before period splitting.
    """

    sheet_name: str = Field(..., min_length=1)
    metric: MetricSpec
    period_a: PeriodSpec
    period_b: PeriodSpec
    group_by: list[str] = Field(default_factory=list)
    filters: list[SafeFilter] = Field(default_factory=list)


class TopNInput(BaseModel):
    """Input model for :func:`~analytics.engine.top_n` and :func:`~analytics.engine.bottom_n`.

    Attributes:
        sheet_name: Target sheet to query.
        category_column: Column to segment/rank by.
        metric: The metric to rank by.
        n: Number of items to return.
        filters: Optional pre-filter.
        descending: ``True`` = top N (highest values first);
            ``False`` = bottom N (lowest values first).
    """

    sheet_name: str = Field(..., min_length=1)
    category_column: str = Field(..., min_length=1)
    metric: MetricSpec
    n: int = Field(10, ge=1, le=500)
    filters: list[SafeFilter] = Field(default_factory=list)
    descending: bool = True


class DescribeColumnInput(BaseModel):
    """Input model for :func:`~analytics.engine.describe_column`.

    Attributes:
        sheet_name: Target sheet to query.
        column: Column to describe.
        filters: Optional pre-filter applied before description.
    """

    sheet_name: str = Field(..., min_length=1)
    column: str = Field(..., min_length=1)
    filters: list[SafeFilter] = Field(default_factory=list)


class PreviewRowsInput(BaseModel):
    """Input model for :func:`~analytics.engine.preview_rows`.

    Attributes:
        sheet_name: Target sheet to preview.
        filters: Optional filter clauses.
        limit: Number of rows to return (capped at 50).
    """

    sheet_name: str = Field(..., min_length=1)
    filters: list[SafeFilter] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=50)


class MakeChartInput(BaseModel):
    """Specification for a chart to render in the UI layer.

    The UI layer reads this schema from :class:`ReportResult` and creates the
    appropriate Matplotlib / Streamlit figure — no computation happens here.

    Attributes:
        chart_type: Chart family identifier.
        x_column: Column for the x-axis (or labels for pie charts).
        y_column: Column for the y-axis (metric values).
        color_column: Optional column used for colour / legend split.
        title: Chart title text.
        x_label: X-axis label override (empty = use column name).
        y_label: Y-axis label override (empty = use column name).
    """

    chart_type: Literal["line", "bar", "hbar", "pie", "scatter", "area"] = "bar"
    x_column: str = Field(..., min_length=1)
    y_column: str = Field(..., min_length=1)
    color_column: str | None = None
    title: str = ""
    x_label: str = ""
    y_label: str = ""


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------

ReportId = Literal[
    "sales_overview",
    "top_products",
    "slow_inventory",
    "receivables_aging",
    "expense_breakdown",
]
"""Identifies one of the five built-in ready-made reports."""


_KPI_ARABIC_LABELS: dict[str, str] = {
    "total revenue": "إجمالي الإيرادات",
    "avg monthly revenue": "متوسط الإيراد الشهري",
    "total transactions": "إجمالي المعاملات",
    "best month": "أفضل شهر",
    "total skus": "إجمالي الأصناف",
    "total services": "إجمالي الخدمات",
    "top product": "المنتج الأكثر مبيعاً",
    "top service": "الخدمة الأكثر طلباً",
    "pareto 80/20 driver": "قاعدة باريتو (80/20)",
    "overall gross margin": "هامش الربح الإجمالي",
    "total slow items": "الأصناف الراكدة",
    "slow items count": "الأصناف الراكدة",
    "total slow stock value": "قيمة المخزون الراكد",
    "total slow stock": "المخزون الراكد",
    "total overdue": "إجمالي المتأخرات",
    "total outstanding": "إجمالي المستحقات",
    "overdue ratio": "نسبة المتأخرات",
    "overdue invoices count": "الفواتير المتأخرة",
    "total expenses": "إجمالي المصروفات",
    "top category": "أعلى فئة مصروفات",
    "total categories": "عدد الفئات",
    "highest expense month": "أعلى شهر بالمصروفات",
}


class KPICard(BaseModel):
    """A single KPI card for display in the report UI.

    Attributes:
        label: Short human-readable label (e.g. 'Total Revenue').
        value: Formatted value string or numeric value.
        label_ar: Optional Arabic label translation.
        unit: Optional unit string.
        delta: Optional delta / trend string or float.
        delta_label: Optional label for the delta.
        delta_positive: ``True`` if delta represents improvement.
        is_good_delta: Alias for delta_positive.
    """

    label: str
    value: Any
    label_ar: str | None = None
    unit: str = ""
    delta: Any = None
    delta_label: str = ""
    delta_positive: bool | None = None
    is_good_delta: bool | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.is_good_delta is None and self.delta_positive is not None:
            self.is_good_delta = self.delta_positive
        elif self.delta_positive is None and self.is_good_delta is not None:
            self.delta_positive = self.is_good_delta

        if not self.label_ar:
            self.label_ar = _KPI_ARABIC_LABELS.get(self.label.strip().lower(), self.label)


class ReportResult(BaseModel):
    """Full result of a built-in report returned by :mod:`analytics.reports`.

    Attributes:
        report_id: Which report was run.
        kpis: KPI cards to display at the top of the report panel.
        tables: Named result tables (each a :class:`ToolResult`).
        charts: Chart specifications aligned with the tables.
        calculation_description: Human-readable explanation of the methodology.
        missing_roles: Roles that were required but not mapped; the report may
            be incomplete or unavailable.
        warnings: Non-fatal informational warnings about data / assumptions.
        error: Non-None when the report failed entirely; tables will be empty.
    """

    report_id: ReportId
    kpis: list[KPICard] = Field(default_factory=list)
    tables: dict[str, ToolResult] = Field(default_factory=dict)
    charts: list[MakeChartInput] = Field(default_factory=list)
    calculation_description: str = ""
    missing_roles: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def is_available(self) -> bool:
        """Return True if all required roles are mapped and no fatal error occurred."""
        return len(self.missing_roles) == 0 and self.error is None

    @property
    def kpi_cards(self) -> list[KPICard]:
        """Backward-compatible alias for kpis."""
        return self.kpis


class RunReportInput(BaseModel):
    """Input model for the :func:`~analytics.reports.run_report` dispatcher.

    Attributes:
        report_id: Which report to run.
        sheet_name: Optional explicit sheet override; engine auto-selects when
            not provided, based on role mapping.
        params: Report-specific parameter overrides (e.g. ``slow_days_threshold``).
    """

    report_id: ReportId
    sheet_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
