from __future__ import annotations

"""Data quality analysis for REMO_OX Analytics.

Generates per-column and per-sheet quality statistics (nulls, parse failures,
outliers, negatives, duplicates) and produces human-readable warning text in
Arabic or English.

Typical usage::

    report = generate_quality_report(sheets, mapping)
    summary = get_summary_text(report, sheet_name="Sheet1", lang="ar")
"""

import re

import pandas as pd

from analytics.schemas import (
    ColumnQualityReport,
    QualityReport,
    SheetQualityReport,
)
from core.logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IQR multiplier for outlier detection
_IQR_FACTOR: float = 1.5

# Maximum number of sample issue values to include per column
_MAX_SAMPLE_ISSUES: int = 3

# Roles for which negative values are considered suspicious
_SUSPICIOUS_NEGATIVE_ROLES: frozenset[str] = frozenset(
    [
        "quantity",
        "unit_price",
        "revenue",
        "stock_qty",
        "unit_cost",
        "cost",
        "invoice_amount",
        "expense_amount",
    ]
)

# Null percentage thresholds for warning levels
_WARN_NULL_HIGH: float = 30.0   # ≥ 30 % → high-severity warning
_WARN_NULL_LOW: float = 5.0     # ≥ 5 % → informational warning

# Outlier count relative to row count that triggers a warning
_WARN_OUTLIER_RATIO: float = 0.05   # ≥ 5 % of rows are outliers

# Keywords indicating total/summary rows (reused from ingest module logic)
_TOTAL_KEYWORDS: frozenset[str] = frozenset(
    [
        "total", "totals", "subtotal", "grand total", "sum", "summary",
        "الإجمالي", "المجموع", "إجمالي", "مجموع", "الكلي", "حصلة",
        "الاجمالى", "اجمالي", "مجموع عام",
    ]
)

# ---------------------------------------------------------------------------
# i18n label dictionaries
# ---------------------------------------------------------------------------

_LABELS: dict[str, dict[str, str]] = {
    "ar": {
        "null_high": "تحذير: عمود '{col}' يحتوي على {pct:.1f}% قيم فارغة",
        "null_low": "ملاحظة: عمود '{col}' يحتوي على {pct:.1f}% قيم فارغة",
        "parse_fail": "تحذير: عمود '{col}' يحتوي على {n} قيمة غير قابلة للتحويل",
        "outlier": "تحذير: عمود '{col}' يحتوي على {n} قيمة شاذة ({pct:.1f}% من الصفوف)",
        "negative": "تحذير: عمود '{col}' (دور: {role}) يحتوي على {n} قيمة سالبة غير متوقعة",
        "duplicates": "تحذير: ورقة '{sheet}' تحتوي على {n} صف مكرر",
        "total_rows": "معلومة: تم استبعاد {n} صف يمثل مجموع/إجمالي",
        "sheet_header": "تقرير جودة البيانات — ورقة: {sheet}",
        "rows": "عدد الصفوف",
        "ok": "لا توجد مشكلات جودة ملحوظة.",
    },
    "en": {
        "null_high": "Warning: column '{col}' has {pct:.1f}% missing values",
        "null_low": "Note: column '{col}' has {pct:.1f}% missing values",
        "parse_fail": "Warning: column '{col}' has {n} unparseable values",
        "outlier": "Warning: column '{col}' has {n} outliers ({pct:.1f}% of rows)",
        "negative": "Warning: column '{col}' (role: {role}) has {n} unexpected negative values",
        "duplicates": "Warning: sheet '{sheet}' has {n} duplicate rows",
        "total_rows": "Info: {n} total/summary rows were excluded",
        "sheet_header": "Data Quality Report — Sheet: {sheet}",
        "rows": "Row count",
        "ok": "No significant quality issues detected.",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_quality_report(
    sheets: dict[str, pd.DataFrame],
    mapping: dict[str, str],
) -> QualityReport:
    """Generate a full quality report for all sheets in the workbook.

    For each sheet the function computes per-column statistics (nulls, parse
    failures, outliers, negatives, unique counts, sample issues) as well as
    sheet-level statistics (duplicates, excluded total rows).  Summary
    warnings are generated for any metric that exceeds configured thresholds.

    Args:
        sheets: Mapping of sheet name → cleaned :class:`pandas.DataFrame` as
            returned by :func:`data.ingest.read_excel`.
        mapping: Flat mapping of ``column_name → role`` (confirmed + derived
            assignments).  Used to identify which columns warrant
            negative-value scrutiny.

    Returns:
        A :class:`~analytics.schemas.QualityReport` with a
        :class:`~analytics.schemas.SheetQualityReport` for every sheet.
    """
    sheet_reports: list[SheetQualityReport] = []
    overall_warnings: list[str] = []

    for sheet_name, df in sheets.items():
        sheet_report = _analyze_sheet(sheet_name, df, mapping)
        sheet_reports.append(sheet_report)

    # Cross-sheet warnings
    total_sheets = len(sheet_reports)
    empty_sheets = [r.sheet_name for r in sheet_reports if r.row_count == 0]
    if empty_sheets:
        overall_warnings.append(
            f"The following sheets contain no data rows: {', '.join(empty_sheets)}"
        )

    if total_sheets == 0:
        overall_warnings.append("No sheets with data were found in the workbook.")

    return QualityReport(sheets=sheet_reports, overall_warnings=overall_warnings)


def get_summary_text(
    report: QualityReport,
    sheet: str,
    lang: str = "ar",
) -> str:
    """Produce a human-readable quality summary for a single sheet.

    Args:
        report: The :class:`~analytics.schemas.QualityReport` to summarise.
        sheet: Name of the sheet to describe.
        lang: Language code — ``"ar"`` for Arabic or ``"en"`` for English.
            Defaults to ``"ar"``.

    Returns:
        A plain-text multi-line string suitable for display in a Streamlit
        ``st.text`` / ``st.markdown`` widget.

    Raises:
        ValueError: If *sheet* is not found in the report.
    """
    if lang not in _LABELS:
        lang = "en"

    lbl = _LABELS[lang]

    sheet_report = next(
        (r for r in report.sheets if r.sheet_name == sheet), None
    )
    if sheet_report is None:
        raise ValueError(
            f"Sheet '{sheet}' not found in quality report. "
            f"Available sheets: {[r.sheet_name for r in report.sheets]}"
        )

    lines: list[str] = [
        lbl["sheet_header"].format(sheet=sheet),
        f"{lbl['rows']}: {sheet_report.row_count}",
        "",
    ]

    all_warnings = sheet_report.warnings[:]

    # Duplicates
    if sheet_report.duplicate_rows > 0:
        all_warnings.append(
            lbl["duplicates"].format(sheet=sheet, n=sheet_report.duplicate_rows)
        )

    # Excluded total rows
    if sheet_report.excluded_total_rows > 0:
        all_warnings.append(
            lbl["total_rows"].format(n=sheet_report.excluded_total_rows)
        )

    if all_warnings:
        lines.extend(all_warnings)
    else:
        lines.append(lbl["ok"])

    # Per-column details
    lines.append("")
    for col_report in sheet_report.columns:
        col_issues: list[str] = []

        if col_report.null_pct >= _WARN_NULL_HIGH:
            col_issues.append(
                lbl["null_high"].format(col=col_report.column, pct=col_report.null_pct)
            )
        elif col_report.null_pct >= _WARN_NULL_LOW:
            col_issues.append(
                lbl["null_low"].format(col=col_report.column, pct=col_report.null_pct)
            )

        if col_report.parse_failures > 0:
            col_issues.append(
                lbl["parse_fail"].format(col=col_report.column, n=col_report.parse_failures)
            )

        if col_report.outliers_count > 0 and sheet_report.row_count > 0:
            pct = 100.0 * col_report.outliers_count / sheet_report.row_count
            col_issues.append(
                lbl["outlier"].format(
                    col=col_report.column, n=col_report.outliers_count, pct=pct
                )
            )

        if col_report.negative_count > 0 and col_report.role:
            col_issues.append(
                lbl["negative"].format(
                    col=col_report.column,
                    role=col_report.role,
                    n=col_report.negative_count,
                )
            )

        lines.extend(col_issues)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _analyze_sheet(
    sheet_name: str,
    df: pd.DataFrame,
    mapping: dict[str, str],
) -> SheetQualityReport:
    """Compute quality statistics for one sheet.

    Args:
        sheet_name: Human-readable name of the sheet.
        df: Cleaned DataFrame for the sheet.
        mapping: Column → role mapping (may be partial).

    Returns:
        A populated :class:`~analytics.schemas.SheetQualityReport`.
    """
    row_count = len(df)
    warnings: list[str] = []

    # Duplicate rows
    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows > 0:
        warnings.append(
            f"Sheet '{sheet_name}' has {duplicate_rows} fully duplicate row(s)."
        )

    # Excluded total rows — detect any remaining after ingestion
    excluded_total = _count_total_rows(df)

    col_reports: list[ColumnQualityReport] = []
    for col in df.columns:
        role = mapping.get(col)
        col_report = _analyze_column(df[col], col, role, row_count)
        col_reports.append(col_report)

        # Emit warnings for this column
        if col_report.null_pct >= _WARN_NULL_HIGH:
            warnings.append(
                f"Column '{col}' has {col_report.null_pct:.1f}% missing values."
            )
        if col_report.parse_failures > 0:
            warnings.append(
                f"Column '{col}' has {col_report.parse_failures} unparseable value(s)."
            )
        if col_report.outliers_count > 0 and row_count > 0:
            outlier_ratio = col_report.outliers_count / row_count
            if outlier_ratio >= _WARN_OUTLIER_RATIO:
                warnings.append(
                    f"Column '{col}' has {col_report.outliers_count} outlier(s) "
                    f"({outlier_ratio * 100:.1f}% of rows)."
                )
        if col_report.negative_count > 0 and role in _SUSPICIOUS_NEGATIVE_ROLES:
            warnings.append(
                f"Column '{col}' (role: {role}) has {col_report.negative_count} "
                "unexpected negative value(s)."
            )

    return SheetQualityReport(
        sheet_name=sheet_name,
        row_count=row_count,
        duplicate_rows=duplicate_rows,
        excluded_total_rows=excluded_total,
        columns=col_reports,
        warnings=warnings,
    )


def _analyze_column(
    series: pd.Series,
    col_name: str,
    role: str | None,
    row_count: int,
) -> ColumnQualityReport:
    """Compute quality statistics for a single column.

    Args:
        series: The column data.
        col_name: Column name (used for display only).
        role: Mapped semantic role, or ``None`` if unmapped.
        row_count: Total rows in the sheet (for percentage calculations).

    Returns:
        A populated :class:`~analytics.schemas.ColumnQualityReport`.
    """
    null_count = int(series.isna().sum())
    null_pct = round(100.0 * null_count / max(row_count, 1), 2)
    unique_count = int(series.nunique(dropna=True))

    parse_failures = 0
    outliers_count = 0
    negative_count = 0
    sample_issues: list[str] = []

    non_null = series.dropna()

    if pd.api.types.is_numeric_dtype(series):
        # Outlier detection via IQR
        q1 = non_null.quantile(0.25)
        q3 = non_null.quantile(0.75)
        iqr = q3 - q1
        lower_fence = q1 - _IQR_FACTOR * iqr
        upper_fence = q3 + _IQR_FACTOR * iqr
        outlier_mask = (non_null < lower_fence) | (non_null > upper_fence)
        outliers_count = int(outlier_mask.sum())

        # Sample outlier values
        if outliers_count > 0:
            outlier_vals = non_null[outlier_mask].head(_MAX_SAMPLE_ISSUES)
            sample_issues.extend([str(v) for v in outlier_vals])

        # Negative count (only meaningful for certain roles)
        if role in _SUSPICIOUS_NEGATIVE_ROLES:
            negative_count = int((non_null < 0).sum())
            if negative_count > 0 and len(sample_issues) < _MAX_SAMPLE_ISSUES:
                neg_vals = non_null[non_null < 0].head(
                    _MAX_SAMPLE_ISSUES - len(sample_issues)
                )
                sample_issues.extend([str(v) for v in neg_vals])

    elif pd.api.types.is_datetime64_any_dtype(series):
        # No outlier detection for dates; just count nulls already captured
        pass

    else:
        # Object column — check for values that look numeric/date but failed
        parse_failures = _count_parse_failures(series)
        if parse_failures > 0:
            failure_samples = _get_parse_failure_samples(series, _MAX_SAMPLE_ISSUES)
            sample_issues.extend(failure_samples)

    # Trim sample_issues to the maximum allowed
    sample_issues = sample_issues[:_MAX_SAMPLE_ISSUES]

    return ColumnQualityReport(
        column=col_name,
        role=role,
        null_count=null_count,
        null_pct=null_pct,
        parse_failures=parse_failures,
        outliers_count=outliers_count,
        negative_count=negative_count,
        unique_count=unique_count,
        sample_issues=sample_issues,
    )


def _count_parse_failures(series: pd.Series) -> int:
    """Count values in an object Series that appear numeric/date but cannot be parsed.

    A "parse failure" is a non-null string that:
    - Contains digit characters (suggesting numeric intent), **and**
    - Cannot be coerced by ``pd.to_numeric`` **and**
    - Cannot be coerced by ``pd.to_datetime``.

    Args:
        series: Object-dtype :class:`pandas.Series`.

    Returns:
        Integer count of parse failures.
    """
    failures = 0
    _digit_re = re.compile(r"\d")

    for val in series.dropna():
        if not isinstance(val, str):
            continue
        stripped = val.strip()
        if not stripped or not _digit_re.search(stripped):
            continue
        # Looks numeric/date — try parsing
        numeric_ok = pd.to_numeric(stripped.replace(",", ""), errors="coerce")
        if pd.notna(numeric_ok):
            continue
        try:
            pd.to_datetime(stripped)
        except Exception:
            failures += 1

    return failures


def _get_parse_failure_samples(series: pd.Series, max_samples: int) -> list[str]:
    """Return a sample of parse-failing values from an object column.

    Args:
        series: Object-dtype :class:`pandas.Series`.
        max_samples: Maximum number of sample strings to return.

    Returns:
        List of up to *max_samples* problematic cell values as strings.
    """
    samples: list[str] = []
    _digit_re = re.compile(r"\d")

    for val in series.dropna():
        if len(samples) >= max_samples:
            break
        if not isinstance(val, str):
            continue
        stripped = val.strip()
        if not stripped or not _digit_re.search(stripped):
            continue
        numeric_ok = pd.to_numeric(stripped.replace(",", ""), errors="coerce")
        if pd.notna(numeric_ok):
            continue
        try:
            pd.to_datetime(stripped)
        except Exception:
            samples.append(stripped)

    return samples


def _count_total_rows(df: pd.DataFrame) -> int:
    """Count any remaining total/summary rows in a (possibly already-cleaned) DataFrame.

    Args:
        df: DataFrame to inspect.

    Returns:
        Integer count of rows identified as total/summary rows.
    """
    count = 0
    for _, row in df.iterrows():
        for val in row:
            if isinstance(val, str):
                cleaned = val.strip().lower()
                if cleaned in _TOTAL_KEYWORDS:
                    count += 1
                    break
                if any(
                    cleaned.startswith(kw + " ") or cleaned.startswith(kw + ":")
                    for kw in _TOTAL_KEYWORDS
                ):
                    count += 1
                    break
    return count
