from __future__ import annotations

"""Logging setup with secret redaction for REMO_OX Analytics.

Sensitive values (API keys, tokens, email addresses) are automatically
redacted from all log output by :class:`RedactingFormatter`.

Raw provider errors go to logs so administrators can diagnose failures;
end users only see friendly messages surfaced by the UI layer.

Usage::

    from core.logging_setup import setup_logging, get_logger

    setup_logging()
    logger = get_logger(__name__)
    logger.info("Application started")
"""

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.security import ValidationResult  # noqa: F401  (type-check only)

# ---------------------------------------------------------------------------
# Redaction patterns
# ---------------------------------------------------------------------------

#: Compiled patterns applied to every formatted log record.
#: Order matters — more specific patterns should come first.
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # OpenAI / Anthropic / generic sk-* API keys
    (re.compile(r"sk-[A-Za-z0-9_\-]{10,}"), "sk-[REDACTED]"),
    # JWT / Supabase / other Base64url tokens starting with eyJ
    (re.compile(r"eyJ[A-Za-z0-9_\-]{20,}"), "eyJ[REDACTED]"),
    # Explicit Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{10,}"), "Bearer [REDACTED]"),
    # Email addresses — redact local part, keep domain for debugging
    (
        re.compile(r"([A-Za-z0-9._%+\-]+)(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"),
        r"[REDACTED]\2",
    ),
]


# ---------------------------------------------------------------------------
# Redacting formatter
# ---------------------------------------------------------------------------


class RedactingFormatter(logging.Formatter):
    """Log formatter that strips secrets and PII from records before output.

    Applies :data:`_REDACT_PATTERNS` to the fully formatted string so that
    multi-line messages and exception tracebacks are also redacted.

    Example::

        fmt = RedactingFormatter("%(levelname)s — %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(fmt)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record and apply secret redaction.

        Args:
            record: The log record to format.

        Returns:
            Formatted, redacted log string.
        """
        original = super().format(record)
        return self._redact(original)

    @staticmethod
    def _redact(text: str) -> str:
        """Apply all redaction patterns to *text*.

        Args:
            text: Raw formatted log string.

        Returns:
            String with sensitive values replaced by redaction markers.
        """
        for pattern, replacement in _REDACT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

#: Standard log format used by all handlers.
_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure application-wide logging.

    Sets up:
    - A :class:`RedactingFormatter`-wrapped ``StreamHandler`` writing to
      ``stdout`` (always active).
    - A :class:`~logging.handlers.RotatingFileHandler` writing to
      ``logs/app.log`` (created only if the filesystem is writable — on
      ephemeral environments like Streamlit Cloud this step is silently
      skipped).

    Noisy third-party loggers (``httpx``, ``litellm``, etc.) are suppressed
    to ``WARNING`` level.

    This function is idempotent: calling it multiple times (e.g. across
    Streamlit re-runs) clears existing handlers before reconfiguring.

    Args:
        level: Root logging level. Defaults to ``logging.INFO``.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to prevent duplicate output on Streamlit re-runs.
    root.handlers.clear()

    formatter = RedactingFormatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ---- Stream handler (always present) ----
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # ---- Rotating file handler (best-effort) ----
    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Ephemeral filesystem (e.g. Streamlit Cloud) — file logging skipped.
        pass

    # ---- Suppress noisy third-party loggers ----
    _noisy_loggers = (
        "httpx",
        "httpcore",
        "urllib3",
        "supabase",
        "litellm",
        "openai",
        "anthropic",
        "postgrest",
        "realtime",
        "gotrue",
    )
    for name in _noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a named :class:`logging.Logger` for *name*.

    Intended to be called at module level::

        logger = get_logger(__name__)

    Args:
        name: Logger name — typically the module's ``__name__``.

    Returns:
        A :class:`logging.Logger` instance inheriting the root configuration
        established by :func:`setup_logging`.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Database error logging helper
# ---------------------------------------------------------------------------

_logger = get_logger(__name__)


def log_error_to_db(
    error: Exception,
    location: str,
    user_id: str | None,
    backend: object,
) -> None:
    """Persist an application error to the ``app_errors`` database table.

    This function is intentionally non-raising: if the database write fails
    for any reason (network error, schema mismatch, etc.) the failure is
    logged locally and the calling code continues uninterrupted.

    The function is synchronous but safe to call from within async contexts
    via ``asyncio.create_task`` or a thread pool.

    Args:
        error: The exception that was caught.
        location: A short string identifying where the error occurred,
            e.g. ``"upload.validate_upload"`` or ``"analytics.sales_overview"``.
        user_id: The authenticated user's ID, or ``None`` for unauthenticated
            requests.
        backend: A backend / database client object. Must expose an
            ``insert_error(table, payload)`` method that accepts a ``dict``.
            If the object does not have this method, the error is only logged
            locally.

    Example::

        from core.logging_setup import log_error_to_db

        try:
            result = risky_operation()
        except Exception as exc:
            log_error_to_db(exc, "module.risky_operation", user_id, db)
            st.error(t("error_generic", lang))
    """
    # Always log locally first so we have a record even if the DB write fails.
    _logger.error(
        "Unhandled error at %s (user=%s): %s: %s",
        location,
        user_id or "anonymous",
        type(error).__name__,
        error,
        exc_info=True,
    )

    insert_fn = getattr(backend, "insert_error", None)
    if insert_fn is None:
        _logger.debug(
            "Backend %r does not expose insert_error(); skipping DB error log.",
            type(backend).__name__,
        )
        return

    import traceback

    payload: dict[str, object] = {
        "location": location,
        "user_id": user_id,
        "error_type": type(error).__name__,
        # Use repr() so that the message is safe to store even if it contains
        # non-ASCII characters. Secrets are not included in exception messages
        # by convention — the RedactingFormatter only applies to log output.
        "error_message": repr(str(error)),
        "traceback": traceback.format_exc(),
    }

    try:
        insert_fn("app_errors", payload)
    except Exception as db_err:
        # Log locally but do not propagate — the app must keep running.
        _logger.warning(
            "Failed to write error record to database (location=%s): %s",
            location,
            db_err,
        )
