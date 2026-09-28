from __future__ import annotations

"""Upload validation, sanitization, and rate-limiting utilities for REMO_OX Analytics.

Security model
--------------
Every uploaded file passes through a layered defence before any data is parsed:

1. **Extension check** — only ``.xlsx`` accepted.
2. **Magic-bytes check** — file must start with the ZIP magic ``PK\\x03\\x04``.
3. **Size check** — enforced against both global settings and per-plan limits.
4. **ZIP-bomb guard** — total uncompressed size and compression ratio checked
   against hard limits before any cell data is read.
5. **Structure check** — openpyxl (read-only mode) verifies row/column counts
   per sheet against configurable maximums.

The :class:`RateLimiter` provides an in-memory, per-user sliding-window rate
limiter backed by a :class:`threading.Lock` so it is safe for concurrent
Streamlit sessions.
"""

import html
import io
import re
import threading
import time
import unicodedata
import zipfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import BaseModel, Field

from core.logging_setup import get_logger

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Accepted file extension (lowercase, with dot).
_ALLOWED_EXTENSION: str = ".xlsx"

#: XLSX files are ZIP archives — verify the ZIP magic bytes.
_ZIP_MAGIC: bytes = b"PK\x03\x04"

#: Absolute ceiling for uncompressed ZIP content (500 MB).
_MAX_UNCOMPRESSED_BYTES: int = 500 * 1024 * 1024

#: Maximum allowed compression ratio (uncompressed / compressed).
#: Legitimate XLSX files rarely exceed 10-20×; 100× is a clear anomaly.
_MAX_COMPRESSION_RATIO: int = 100

#: Characters forbidden in sanitised filenames.
_CONTROL_CHAR_RE: re.Pattern[str] = re.compile(r"[\x00-\x1f\x7f]")

#: Path-separator characters that must be stripped from filenames.
_PATH_SEP_CHARS: frozenset[str] = frozenset("/\\:*?\"<>|")

#: Maximum length (characters) for a sanitised filename including extension.
_MAX_FILENAME_LENGTH: int = 200


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Structured result returned by :func:`validate_upload`.

    Attributes:
        is_valid: ``True`` when all checks passed and the file is safe to use.
        errors: Human-readable error descriptions (UI-layer localisation is
            the caller's responsibility). Empty when ``is_valid`` is ``True``.
        sheet_row_counts: Mapping of sheet name → number of data rows (
            excluding the header row). Populated only on success.
        sheet_column_counts: Mapping of sheet name → number of columns.
            Populated only on success.
    """

    is_valid: bool = Field(default=True)
    errors: list[str] = Field(default_factory=list)
    sheet_row_counts: dict[str, int] = Field(default_factory=dict)
    sheet_column_counts: dict[str, int] = Field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """Append an error and mark the result as invalid.

        Args:
            message: Human-readable error description.
        """
        self.is_valid = False
        self.errors.append(message)


# ---------------------------------------------------------------------------
# Internal ZIP-bomb check
# ---------------------------------------------------------------------------


def _check_zip_bomb(file_bytes: bytes) -> tuple[bool, str]:
    """Inspect the ZIP central directory for zip-bomb indicators.

    This check operates entirely on the ZIP metadata (central directory)
    without decompressing any entry content, so it is fast and safe.

    Args:
        file_bytes: Raw file contents.

    Returns:
        A ``(is_safe, error_message)`` tuple. ``error_message`` is an empty
        string when ``is_safe`` is ``True``.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            info_list = zf.infolist()
            total_uncompressed: int = sum(entry.file_size for entry in info_list)
            total_compressed: int = sum(entry.compress_size for entry in info_list)

            if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                size_mb = total_uncompressed // (1024 * 1024)
                return (
                    False,
                    f"File uncompressed content is too large ({size_mb} MB). "
                    f"Maximum allowed is {_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB.",
                )

            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > _MAX_COMPRESSION_RATIO:
                    return (
                        False,
                        f"Suspicious compression ratio detected ({ratio:.0f}×). "
                        "The file may be a zip bomb.",
                    )

        return True, ""

    except zipfile.BadZipFile:
        return False, "File is not a valid ZIP/XLSX archive."
    except Exception as exc:
        return False, f"Could not inspect file structure: {exc}"


# ---------------------------------------------------------------------------
# Plan limits helper
# ---------------------------------------------------------------------------


def _plan_max_file_mb(user_plan: Any) -> int:
    """Return the maximum upload size in MB for *user_plan*.

    Supports plan objects with max_file_mb attribute or plan identifier strings.
    """
    if hasattr(user_plan, "max_file_mb") and isinstance(user_plan.max_file_mb, int):
        return user_plan.max_file_mb
    plan_str = getattr(user_plan, "id", user_plan)
    if isinstance(plan_str, str):
        _plan_limits: dict[str, int] = {
            "trial": 5,
            "starter": 10,
            "basic": 20,
            "pro": 50,
            "enterprise": 200,
        }
        return _plan_limits.get(plan_str.lower(), 5)
    return 5


# ---------------------------------------------------------------------------
# Public API — upload validation
# ---------------------------------------------------------------------------


def validate_upload(
    file_bytes: bytes,
    filename: str,
    user_plan: str,
    settings: object,
) -> ValidationResult:
    """Validate an uploaded file through a layered security pipeline.

    The validation pipeline is short-circuiting: the first critical failure
    (extension, magic bytes, or ZIP bomb) stops further processing so that
    no untrusted content is parsed by openpyxl.

    Args:
        file_bytes: Raw uploaded file contents.
        filename: Original filename as reported by the browser/client.
        user_plan: The uploading user's subscription plan identifier.
            Used to enforce per-plan file-size limits.
        settings: Application :class:`~core.config.Settings` instance
            (or any object exposing ``max_upload_mb``, ``max_rows``,
            and ``max_columns`` integer attributes).

    Returns:
        A :class:`ValidationResult` describing the outcome.
        ``is_valid`` is ``True`` only when every check passed.

    Example::

        from core.security import validate_upload
        from core.config import get_settings

        result = validate_upload(raw_bytes, "sales.xlsx", "pro", get_settings())
        if not result.is_valid:
            for err in result.errors:
                st.error(err)
    """
    result = ValidationResult()

    # ------------------------------------------------------------------
    # 1. Extension check
    # ------------------------------------------------------------------
    suffix = PurePosixPath(filename).suffix.lower() or PureWindowsPath(filename).suffix.lower()
    if suffix != _ALLOWED_EXTENSION:
        result.add_error(
            f"Only '{_ALLOWED_EXTENSION}' files are accepted. "
            f"Received: '{suffix or '(none)'}'"
        )
        return result  # No point continuing — openpyxl won't open it anyway.

    # ------------------------------------------------------------------
    # 2. Magic bytes check
    # ------------------------------------------------------------------
    if file_bytes[:4] != _ZIP_MAGIC:
        result.add_error(
            "File does not have valid XLSX/ZIP headers. "
            "The file may be corrupt or misnamed."
        )
        return result

    # ------------------------------------------------------------------
    # 3. Size check (global settings limit)
    # ------------------------------------------------------------------
    global_max_bytes: int = int(settings.max_upload_mb) * 1024 * 1024
    if len(file_bytes) > global_max_bytes:
        result.add_error(
            f"File size ({len(file_bytes) // (1024 * 1024)} MB) exceeds the "
            f"global limit of {settings.max_upload_mb} MB."
        )
        return result

    # ------------------------------------------------------------------
    # 3b. Size check (per-plan limit)
    # ------------------------------------------------------------------
    plan_max_mb: int = _plan_max_file_mb(user_plan)
    plan_max_bytes: int = plan_max_mb * 1024 * 1024
    if len(file_bytes) > plan_max_bytes:
        result.add_error(
            f"File size ({len(file_bytes) // (1024 * 1024)} MB) exceeds the "
            f"limit for your '{user_plan}' plan ({plan_max_mb} MB). "
            "Please upgrade your plan or reduce the file size."
        )
        return result

    # ------------------------------------------------------------------
    # 4. ZIP-bomb guard
    # ------------------------------------------------------------------
    is_safe, bomb_error = _check_zip_bomb(file_bytes)
    if not is_safe:
        _logger.warning(
            "ZIP-bomb check failed for filename=%r (plan=%s): %s",
            filename,
            user_plan,
            bomb_error,
        )
        result.add_error(
            "File rejected for security reasons. Please upload a valid Excel file."
        )
        return result

    # ------------------------------------------------------------------
    # 5. Structure check via openpyxl (read-only — no formula evaluation)
    # ------------------------------------------------------------------
    try:
        import openpyxl

        wb = openpyxl.load_workbook(
            io.BytesIO(file_bytes),
            read_only=True,
            data_only=True,
            keep_links=False,
        )

        max_rows: int = int(settings.max_rows)
        max_cols: int = int(settings.max_columns)

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]

            # openpyxl may report None for dimensions on empty sheets.
            row_count: int = ws.max_row or 0
            col_count: int = ws.max_column or 0

            # Subtract 1 to exclude the header row (conservative — the
            # caller may refine this after full parsing).
            data_rows: int = max(0, row_count - 1)

            if data_rows > max_rows:
                result.add_error(
                    f"Sheet '{sheet_name}' has {data_rows:,} data rows, "
                    f"which exceeds the limit of {max_rows:,} rows."
                )

            if col_count > max_cols:
                result.add_error(
                    f"Sheet '{sheet_name}' has {col_count} columns, "
                    f"which exceeds the limit of {max_cols} columns."
                )

            result.sheet_row_counts[sheet_name] = data_rows
            result.sheet_column_counts[sheet_name] = col_count

        wb.close()

    except Exception as exc:
        _logger.error("openpyxl failed to open uploaded file: %s", exc, exc_info=True)
        result.add_error(
            f"File is corrupt or cannot be parsed as a valid Excel workbook: {exc}"
        )
        return result

    if result.errors:
        result.is_valid = False

    return result


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------


def sanitize_filename(name: str) -> str:
    """Return a sanitised version of *name* safe for use as a stored filename.

    Transformations applied (in order):
    1. Strip leading/trailing whitespace.
    2. Remove all path-separator and Windows-reserved characters.
    3. Remove null bytes and ASCII control characters.
    4. Normalise Unicode to NFC form.
    5. Truncate to :data:`_MAX_FILENAME_LENGTH` characters, preserving the
       ``.xlsx`` extension.
    6. Ensure the result ends with ``.xlsx``; if the stem becomes empty
       after sanitisation, fall back to ``"upload.xlsx"``.

    Args:
        name: Original filename, as reported by the file uploader.

    Returns:
        A sanitised filename string ending in ``.xlsx``.

    Example::

        sanitize_filename("../../etc/passwd.xlsx")  # → "etcpasswd.xlsx"
        sanitize_filename("My Sales 2024.xlsx")      # → "My Sales 2024.xlsx"
    """
    if not name:
        return "upload.xlsx"

    # Normalise Unicode (NFC) to avoid homoglyph tricks.
    name = unicodedata.normalize("NFC", name)

    # Strip path separators and reserved characters.
    cleaned = "".join(ch for ch in name if ch not in _PATH_SEP_CHARS)

    # Remove null bytes and ASCII control characters.
    cleaned = _CONTROL_CHAR_RE.sub("", cleaned)

    # Strip leading/trailing whitespace and dots (Windows hidden-file trick).
    cleaned = cleaned.strip(". \t\r\n")

    if not cleaned:
        return "upload.xlsx"

    # Separate stem and extension.
    p = PurePosixPath(cleaned)
    stem = p.stem or "upload"
    # Always force .xlsx extension regardless of what the sanitised name says.
    extension = _ALLOWED_EXTENSION

    # Truncate stem so that total length (stem + extension) ≤ max.
    max_stem_len = _MAX_FILENAME_LENGTH - len(extension)
    if len(stem) > max_stem_len:
        stem = stem[:max_stem_len]

    return f"{stem}{extension}"


# ---------------------------------------------------------------------------
# HTML escaping for display
# ---------------------------------------------------------------------------


def escape_for_display(text: str) -> str:
    """HTML-escape *text* before embedding in Streamlit markdown/HTML output.

    Use this whenever user-supplied content (filenames, column names, free-text
    inputs) is included in strings passed to ``st.markdown`` or
    ``st.write`` with ``unsafe_allow_html=True``.

    Args:
        text: Raw user-provided string.

    Returns:
        HTML-escaped string safe for injection into HTML contexts.

    Example::

        safe = escape_for_display(user_filename)
        st.markdown(f"<b>File:</b> {safe}", unsafe_allow_html=True)
    """
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# In-memory rate limiter
# ---------------------------------------------------------------------------

#: Module-level state for the rate limiter.  Protected by :data:`_rl_lock`.
#: Structure: { user_id → [timestamp_monotonic, ...] }
_rl_state: dict[str, list[float]] = {}
_rl_lock: threading.Lock = threading.Lock()


class RateLimiter:
    """Thread-safe, per-user sliding-window token-bucket rate limiter.

    Tracks message timestamps in a deque per user. On each call to
    :meth:`check_and_consume`, timestamps older than the window are evicted
    before the check is performed, so memory usage is bounded.

    This implementation is intentionally in-process (no Redis or external
    state). It resets on process restart, which is acceptable for the
    Streamlit single-server deployment model.

    Args:
        max_tokens: Maximum number of tokens allowed within *window_seconds*.
        window_seconds: Length of the sliding window in seconds.

    Example::

        limiter = RateLimiter(max_tokens=20, window_seconds=60)

        if limiter.check_and_consume(user_id="abc123"):
            # proceed with AI call
            ...
        else:
            st.warning("Rate limit reached. Please wait.")
    """

    def __init__(self, max_tokens: int = 20, window_seconds: float = 60.0) -> None:
        """Initialise the rate limiter.

        Args:
            max_tokens: Token budget per window. Defaults to 20.
            window_seconds: Window duration in seconds. Defaults to 60.
        """
        if max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be > 0, got {window_seconds}")

        self._max_tokens: int = max_tokens
        self._window: float = window_seconds

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evict_old(self, timestamps: list[float], now: float) -> None:
        """Remove timestamps that fall outside the current sliding window.

        Args:
            timestamps: Mutable list of monotonic timestamps for a user.
            now: Current ``time.monotonic()`` value.
        """
        cutoff = now - self._window
        # Evict from the front (oldest entries first).
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_consume(self, user_id: str, cost: int = 1) -> bool:
        """Check whether *user_id* has tokens available and consume them.

        Args:
            user_id: Unique identifier for the requesting user.
            cost: Number of tokens to consume. Defaults to 1.

        Returns:
            ``True`` if the request is within the rate limit (tokens were
            consumed). ``False`` if the user is rate-limited.
        """
        if cost < 1:
            raise ValueError(f"cost must be >= 1, got {cost}")

        now = time.monotonic()
        with _rl_lock:
            if user_id not in _rl_state:
                _rl_state[user_id] = []
            timestamps = _rl_state[user_id]
            self._evict_old(timestamps, now)

            if len(timestamps) + cost > self._max_tokens:
                return False

            for _ in range(cost):
                timestamps.append(now)
            return True

    def remaining(self, user_id: str) -> int:
        """Return the number of tokens remaining for *user_id* right now.

        Args:
            user_id: Unique identifier for the requesting user.

        Returns:
            Number of tokens that can still be consumed in the current window.
            Returns :attr:`_max_tokens` if the user has no recorded activity.
        """
        now = time.monotonic()
        with _rl_lock:
            if user_id not in _rl_state:
                return self._max_tokens
            timestamps = _rl_state[user_id]
            self._evict_old(timestamps, now)
            return max(0, self._max_tokens - len(timestamps))

    def reset(self, user_id: str) -> None:
        """Clear all recorded activity for *user_id*.

        Intended for use in tests and admin tooling.

        Args:
            user_id: Unique identifier for the user to reset.
        """
        with _rl_lock:
            _rl_state.pop(user_id, None)
