from __future__ import annotations

"""Excel file ingestion: reading, header detection, and data cleaning.

All parsing is deterministic and never calls the LLM. This module is the
entry point for all uploaded data and must handle real-world messy files.

Typical usage::

    result = read_excel(file_bytes, dayfirst=True)
    df = result.sheets["Sheet1"]
"""

import io
import re
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from core.logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Arabic-Indic digit mapping
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Common currency symbols / codes to strip
_CURRENCY_PATTERN = re.compile(
    r"[\$£€¥₹₽]"
    r"|EGP|USD|EUR|SAR|AED|KWD|BHD|QAR|OMR"
    r"|ج\.م\.?|LE|ل\.ع|ر\.س|د\.إ",
    re.IGNORECASE,
)

# Total / summary row detection keywords (lower-cased for comparison)
_TOTAL_KEYWORDS: frozenset[str] = frozenset(
    [
        "total",
        "totals",
        "subtotal",
        "grand total",
        "sum",
        "summary",
        "الإجمالي",
        "المجموع",
        "إجمالي",
        "مجموع",
        "الكلي",
        "حصلة",
        "الاجمالى",
        "اجمالي",
        "مجموع عام",
    ]
)

# Arabic month names → month number
_AR_MONTHS: dict[str, int] = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "أبريل": 4,
    "ابريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "سبتمبر": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
    "كانون الثاني": 1,
    "شباط": 2,
    "آذار": 3,
    "نيسان": 4,
    "أيار": 5,
    "حزيران": 6,
    "تموز": 7,
    "آب": 8,
    "أيلول": 9,
    "تشرين الأول": 10,
    "تشرين الثاني": 11,
    "كانون الأول": 12,
}

# Parentheses-negative pattern:  (1,234.56)  → -1234.56
_PAREN_NEGATIVE = re.compile(r"^\s*\(([0-9,\.]+)\)\s*$")

# Trailing-minus pattern:  1234-  → -1234
_TRAILING_MINUS = re.compile(r"^\s*([0-9,\.]+)-\s*$")

# Percentage pattern:  45%  → 45.0
_PERCENTAGE = re.compile(r"^\s*(-?[0-9,\.]+)\s*%\s*$")

# Maximum number of rows to scan for header detection
_MAX_HEADER_SCAN = 20

# Excel epoch base
_EXCEL_EPOCH = pd.Timestamp("1899-12-30")

# ---------------------------------------------------------------------------
# Public result container
# ---------------------------------------------------------------------------


class IngestResult:
    """Result of Excel ingestion for all sheets.

    Attributes:
        sheets: Mapping of sheet name → cleaned :class:`pandas.DataFrame`.
        header_rows: Mapping of sheet name → 0-based index of the detected
            header row within the original worksheet.
        excluded_rows: Mapping of sheet name → list of 0-based row indices
            that were removed as total/summary rows.
        sheet_names: Ordered list of sheet names present in the workbook.
    """

    def __init__(
        self,
        sheets: dict[str, pd.DataFrame],
        header_rows: dict[str, int],
        excluded_rows: dict[str, list[int]],
        sheet_names: list[str],
    ) -> None:
        """Initialise ingestion result.

        Args:
            sheets: Cleaned DataFrames keyed by sheet name.
            header_rows: 0-based header row index per sheet.
            excluded_rows: Excluded row indices per sheet.
            sheet_names: Ordered list of all sheet names.
        """
        self.sheets: dict[str, pd.DataFrame] = sheets
        self.header_rows: dict[str, int] = header_rows
        self.excluded_rows: dict[str, list[int]] = excluded_rows
        self.sheet_names: list[str] = sheet_names

    def __repr__(self) -> str:
        """Return a concise developer-friendly string representation."""
        sheet_summary = ", ".join(
            f"{n}({len(df)}r×{len(df.columns)}c)" for n, df in self.sheets.items()
        )
        return f"IngestResult([{sheet_summary}])"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_excel(file_bytes: bytes, dayfirst: bool = False) -> IngestResult:
    """Read and clean all sheets from an Excel workbook binary.

    The function:

    1. Uses *openpyxl* to detect the true header row (skipping blank leading
       rows and merged-cell banners).
    2. Re-reads each sheet with *pandas* ``read_excel``, supplying the
       detected ``header`` row.
    3. Runs the full cleaning pipeline on every sheet:
       Arabic-Indic normalisation, currency stripping, parentheses/trailing-
       minus negatives, percentage conversion, numeric coercion, date parsing,
       whitespace trimming, and total-row exclusion.
    4. Returns an :class:`IngestResult` with cleaned DataFrames and metadata.

    Args:
        file_bytes: Raw bytes of the ``.xlsx`` / ``.xls`` workbook.
        dayfirst: When ``True``, ambiguous dates like ``01/02/2024`` are
            interpreted as 1 Feb rather than Jan 2nd.  Passed through to
            :func:`_parse_dates`.

    Returns:
        An :class:`IngestResult` containing cleaned DataFrames and metadata.

    Raises:
        ValueError: If ``file_bytes`` cannot be parsed as a valid workbook.
    """
    try:
        wb = load_workbook(
            io.BytesIO(file_bytes), data_only=True, read_only=False
        )
    except Exception as exc:
        raise ValueError(
            f"Unable to open workbook: {exc}.  "
            "Ensure the file is a valid .xlsx or .xlsm file."
        ) from exc

    sheet_names: list[str] = wb.sheetnames
    sheets: dict[str, pd.DataFrame] = {}
    header_rows: dict[str, int] = {}
    excluded_rows: dict[str, list[int]] = {}

    for name in sheet_names:
        ws = wb[name]

        # Skip completely empty sheets
        if ws.max_row is None or ws.max_row == 0:
            logger.info("Sheet '%s' is empty — skipping.", name)
            continue

        header_row_idx = _detect_header_row(ws, max_scan=_MAX_HEADER_SCAN)
        logger.debug("Sheet '%s': detected header row index %d.", name, header_row_idx)

        # Re-read with pandas using detected header row
        try:
            df = pd.read_excel(
                io.BytesIO(file_bytes),
                sheet_name=name,
                header=header_row_idx,
                dtype=object,  # keep everything as object; we coerce later
            )
        except Exception as exc:
            logger.warning("Failed to read sheet '%s': %s — skipping.", name, exc)
            continue

        # Drop fully-empty rows and columns
        df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)

        # Deduplicate column names (in-place mutates the list, returns new list)
        df.columns = _deduplicate_columns([str(c) for c in df.columns])

        # Identify and remove total/summary rows before cleaning
        total_mask = df.apply(_is_total_row, axis=1)
        excl: list[int] = df.index[total_mask].tolist()
        df = df[~total_mask].reset_index(drop=True)

        # Run cleaning pipeline
        df = _clean_dataframe(df, dayfirst=dayfirst)

        sheets[name] = df
        header_rows[name] = header_row_idx
        excluded_rows[name] = excl

    return IngestResult(
        sheets=sheets,
        header_rows=header_rows,
        excluded_rows=excluded_rows,
        sheet_names=sheet_names,
    )


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------


def _detect_header_row(ws: Any, max_scan: int = 20) -> int:
    """Detect the 0-based row index of the real header row in a worksheet.

    Strategy: scan the first ``max_scan`` rows and score each row by the
    number of non-empty *text* cells it contains (openpyxl cell values that
    are ``str``).  The row with the highest text-cell count is chosen as the
    header, with ties broken in favour of the earlier row.

    Merged-cell top banners usually contain 0–1 distinct text cells spread
    across many columns, so the actual column-header row reliably wins.

    Args:
        ws: An *openpyxl* ``Worksheet`` object.
        max_scan: Maximum number of rows to evaluate.

    Returns:
        0-based integer index of the detected header row.
    """
    best_row: int = 0
    best_score: int = -1

    for row_idx, row in enumerate(ws.iter_rows(max_row=max_scan)):
        if row_idx >= max_scan:
            break

        text_cells = sum(
            1
            for cell in row
            if cell.value is not None and isinstance(cell.value, str) and cell.value.strip()
        )

        # Prefer rows with more distinct non-empty text cells
        if text_cells > best_score:
            best_score = text_cells
            best_row = row_idx

    return best_row


# ---------------------------------------------------------------------------
# Cleaning pipeline
# ---------------------------------------------------------------------------


def _clean_dataframe(df: pd.DataFrame, dayfirst: bool = False) -> pd.DataFrame:
    """Apply the full cleaning pipeline to a single sheet DataFrame.

    Pipeline (applied column-by-column):

    1. Trim leading/trailing whitespace from string cells.
    2. Normalise Arabic-Indic digits.
    3. Strip currency symbols.
    4. Parse parentheses-negatives and trailing-minus.
    5. Parse percentage strings.
    6. Attempt numeric coercion via :func:`_normalize_numeric`.
    7. Attempt date coercion via :func:`_parse_dates`.

    Columns that successfully convert to ``datetime64`` are kept as dates;
    columns that convert to numeric (int/float) are kept as numeric;
    the rest remain as ``object`` (string).

    Note:
        Displayed column values are **never** replaced by the Arabic character
        normalisation used for matching.  Use :func:`_normalize_arabic_for_matching`
        on a copy when doing fuzzy lookups.

    Args:
        df: Raw DataFrame from ``pd.read_excel``.
        dayfirst: Passed to :func:`_parse_dates`.

    Returns:
        Cleaned :class:`pandas.DataFrame` with the same columns.
    """
    cleaned = df.copy()

    for col in cleaned.columns:
        series = cleaned[col]

        # Step 1 — stringify + trim where values are strings
        str_mask = series.apply(lambda x: isinstance(x, str))
        if str_mask.any():
            series = series.where(~str_mask, series.map(lambda x: x.strip() if isinstance(x, str) else x))

        # Step 2 — normalise Arabic-Indic digits in string values
        str_mask = series.apply(lambda x: isinstance(x, str))
        if str_mask.any():
            series = series.map(
                lambda x: _normalize_arabic_digits(x) if isinstance(x, str) else x
            )

        # Step 3 — strip currency symbols
        str_mask = series.apply(lambda x: isinstance(x, str))
        if str_mask.any():
            series = series.map(
                lambda x: _CURRENCY_PATTERN.sub("", x).strip() if isinstance(x, str) else x
            )

        # Steps 4 & 5 — parentheses-negative, trailing-minus, percentage
        str_mask = series.apply(lambda x: isinstance(x, str))
        if str_mask.any():
            series = series.map(_parse_special_numeric_string)

        cleaned[col] = series

        # Step 6 — try numeric coercion
        numeric_candidate = _normalize_numeric(series)
        if numeric_candidate is not None:
            cleaned[col] = numeric_candidate
            continue

        # Step 7 — try date coercion (only on object columns)
        if series.dtype == object:
            date_candidate = _parse_dates(series, dayfirst=dayfirst)
            if date_candidate is not None:
                cleaned[col] = date_candidate

    return cleaned


def _parse_special_numeric_string(value: Any) -> Any:
    """Transform parentheses-negatives, trailing-minus, and percentages.

    Handles:
    - ``(1,234)`` → ``-1234.0``
    - ``1,234-`` → ``-1234.0``
    - ``45%`` → ``45.0``

    Non-string or non-matching values are returned unchanged.

    Args:
        value: A single cell value.

    Returns:
        Transformed numeric float, or the original value if no pattern matched.
    """
    if not isinstance(value, str):
        return value

    # Parentheses negative
    m = _PAREN_NEGATIVE.match(value)
    if m:
        try:
            return -float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Trailing minus
    m = _TRAILING_MINUS.match(value)
    if m:
        try:
            return -float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Percentage
    m = _PERCENTAGE.match(value)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    return value


# ---------------------------------------------------------------------------
# Numeric normalisation
# ---------------------------------------------------------------------------


def _normalize_numeric(series: pd.Series) -> pd.Series | None:
    """Attempt to coerce a Series to numeric dtype.

    Strips thousands-separator commas from string values, then tries
    ``pd.to_numeric``.  Returns ``None`` if fewer than 50 % of non-null
    values parse successfully (i.e. the column is not predominantly numeric).

    Args:
        series: Input :class:`pandas.Series` (any dtype).

    Returns:
        A numeric ``pd.Series`` if conversion is feasible, otherwise ``None``.
    """
    # Already numeric — nothing to do
    if pd.api.types.is_numeric_dtype(series):
        return series

    # Work on a string copy; non-strings pass through unchanged
    coerced = series.map(
        lambda x: x.replace(",", "") if isinstance(x, str) else x
    )
    numeric = pd.to_numeric(coerced, errors="coerce")

    non_null = series.notna().sum()
    if non_null == 0:
        return None

    success_rate = numeric.notna().sum() / non_null
    if success_rate >= 0.5:
        return numeric

    return None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _parse_dates(series: pd.Series, dayfirst: bool = False) -> pd.Series | None:
    """Attempt to coerce a Series to ``datetime64`` dtype.

    Handles the following date representations in order:

    1. Already a Python ``datetime``/``date`` object (from openpyxl).
    2. Excel date serial number (integer or float, e.g. ``44927``).
    3. Arabic month-name strings (e.g. ``"15 يناير 2024"``).
    4. ``pd.to_datetime`` with ``dayfirst`` flag (ISO, ``dd/mm/yyyy``,
       ``mm/dd/yyyy``, and many other formats).

    Returns ``None`` if fewer than 50 % of non-null values parse
    successfully, meaning the column is not a date column.

    Args:
        series: Input :class:`pandas.Series`.
        dayfirst: Treat ``01/02/2024`` as 1 Feb (``True``) or Jan 2 (``False``).

    Returns:
        A ``datetime64``-dtype ``pd.Series`` or ``None``.
    """
    import datetime as dt

    def _try_parse_single(val: Any) -> pd.Timestamp | float:
        """Return a Timestamp or NaT for one cell value."""
        if pd.isna(val):
            return pd.NaT

        # Already a date/datetime
        if isinstance(val, (dt.datetime, dt.date)):
            return pd.Timestamp(val)

        # Excel serial number: openpyxl returns int/float for these
        # Plausible Excel serial range: 1 (Jan 1 1900) to ~60000 (year 2064)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and 1 <= val <= 60000:
            try:
                return _EXCEL_EPOCH + pd.Timedelta(days=float(val))
            except Exception:
                pass

        if isinstance(val, str):
            val_stripped = val.strip()
            if not val_stripped:
                return pd.NaT

            # Arabic month names
            for ar_month, month_num in _AR_MONTHS.items():
                if ar_month in val_stripped:
                    # Try patterns: "15 يناير 2024" or "يناير 2024"
                    replaced = val_stripped.replace(ar_month, str(month_num))
                    try:
                        return pd.to_datetime(replaced, dayfirst=True)
                    except Exception:
                        pass

            # Standard parse
            try:
                return pd.to_datetime(val_stripped, dayfirst=dayfirst)
            except Exception:
                return pd.NaT

        return pd.NaT

    parsed = series.map(_try_parse_single)
    non_null = series.notna().sum()
    if non_null == 0:
        return None

    success_rate = parsed.notna().sum() / non_null
    if success_rate >= 0.5:
        return pd.to_datetime(parsed, errors="coerce")

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_arabic_digits(text: str) -> str:
    """Replace Arabic-Indic digit characters with Western ASCII digits.

    Args:
        text: Input string potentially containing ``٠١٢٣٤٥٦٧٨٩``.

    Returns:
        String with Arabic-Indic digits replaced by ``0–9``.
    """
    return text.translate(_AR_DIGITS)


def _is_total_row(row: pd.Series) -> bool:
    """Determine whether a DataFrame row represents a total / summary row.

    A row is classified as a total row if any of its string-valued cells
    (case-insensitive, after stripping whitespace) exactly matches one of the
    keywords in :data:`_TOTAL_KEYWORDS`, or if the keyword appears as a
    prefix of the cell value (e.g. ``"Total Sales"``).

    Args:
        row: A :class:`pandas.Series` representing one DataFrame row.

    Returns:
        ``True`` if the row is a total/summary row, ``False`` otherwise.
    """
    for val in row:
        if not isinstance(val, str):
            continue
        cleaned = val.strip().lower()
        if cleaned in _TOTAL_KEYWORDS:
            return True
        # Keyword appears at start of cell: "Total Sales" → match "total"
        for kw in _TOTAL_KEYWORDS:
            if cleaned.startswith(kw + " ") or cleaned.startswith(kw + ":"):
                return True
    return False


def _deduplicate_columns(columns: list[str]) -> list[str]:
    """Suffix duplicate column names with ``_2``, ``_3``, … to make them unique.

    The first occurrence of a duplicated name is kept as-is; subsequent
    occurrences receive an incrementing numeric suffix.

    Args:
        columns: List of column name strings (may contain duplicates).

    Returns:
        New list of column name strings guaranteed to be unique.

    Example:
        >>> _deduplicate_columns(["A", "B", "A", "A"])
        ['A', 'B', 'A_2', 'A_3']
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for col in columns:
        if col not in seen:
            seen[col] = 1
            result.append(col)
        else:
            seen[col] += 1
            result.append(f"{col}_{seen[col]}")
    return result


def _normalize_arabic_for_matching(text: str) -> str:
    """Normalise Arabic character variants for fuzzy comparison only.

    Replaces:
    - ``أ``, ``إ``, ``آ`` → ``ا``
    - ``ى`` → ``ي``
    - ``ة`` → ``ه``

    This function must **never** be applied to displayed values; use it only
    on a copy of the text when performing matching or similarity scoring.

    Args:
        text: Arabic (or mixed) string to normalise.

    Returns:
        Normalised string with character variants collapsed.
    """
    text = re.sub(r"[أإآ]", "ا", text)
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    return text
