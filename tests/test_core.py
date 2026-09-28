from __future__ import annotations

"""Unit tests for core/config.py, core/logging_setup.py, and core/i18n.py."""

import logging

from pydantic import SecretStr

from core.config import Settings
from core.i18n import get_rtl_css, t
from core.logging_setup import RedactingFormatter


def test_settings_properties() -> None:
    """Settings correctly parses lists and detects local mode."""
    s = Settings(
        admin_emails="Admin1@example.com, Admin2@example.com ",
        supabase_url="",
        supabase_anon_key=SecretStr(""),
    )
    assert s.is_local_mode is True
    assert s.admin_emails_list == ["admin1@example.com", "admin2@example.com"]
    assert s.max_upload_bytes == s.max_upload_mb * 1024 * 1024


def test_settings_validation_warnings() -> None:
    """Settings flags missing LLM keys or admin emails."""
    s = Settings(llm_model="", admin_emails="")
    warnings = s.validate_startup()
    assert any("LLM_MODEL" in w for w in warnings)
    assert any("ADMIN_EMAILS" in w for w in warnings)


def test_redacting_formatter() -> None:
    """RedactingFormatter masks sensitive secrets and emails."""
    formatter = RedactingFormatter(fmt="%(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="API key: sk-abcdef1234567890, Token: Bearer eyJhbGciOiJIUzI1NiJ9.test, User: secretuser@company.com",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    assert "sk-abcdef" not in output
    assert "sk-[REDACTED]" in output
    assert "Bearer [REDACTED]" in output
    assert "secretuser@" not in output
    assert "[REDACTED]@company.com" in output


def test_i18n_translation() -> None:
    """i18n translates keys in Arabic and English with fallbacks."""
    ar_title = t("app_title", lang="ar")
    en_title = t("app_title", lang="en")
    assert ar_title == "REMO_OX Analytics"
    assert en_title == "REMO_OX Analytics"

    ar_upload = t("upload_title", lang="ar")
    en_upload = t("upload_title", lang="en")
    assert "رفع" in ar_upload
    assert "Upload" in en_upload

    # Missing key returns key itself
    assert t("non_existent_key_12345") == "non_existent_key_12345"

    # RTL css
    css = get_rtl_css()
    assert "direction: rtl" in css


def test_logging_setup_and_get_logger() -> None:
    """setup_logging initializes root logger and get_logger returns logger."""
    from core.logging_setup import get_logger, setup_logging
    setup_logging(level=logging.DEBUG)
    logger = get_logger("test_module")
    assert logger.name == "test_module"


def test_get_settings_cached() -> None:
    """get_settings returns cached Settings instance."""
    from core.config import get_settings
    settings = get_settings()
    assert settings.app_name == "REMO_OX Analytics"

