from __future__ import annotations

"""Unit tests for core/security.py."""

import io
import zipfile
from pathlib import Path

from core.config import Settings
from core.security import (
    RateLimiter,
    escape_for_display,
    sanitize_filename,
    validate_upload,
)

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def test_sanitize_filename() -> None:
    """sanitize_filename cleans malicious or abnormal filenames."""
    assert sanitize_filename("../../etc/passwd.xlsx") == "etcpasswd.xlsx"
    assert sanitize_filename("my\x00file.xlsx") == "myfile.xlsx"
    assert sanitize_filename("report.csv") == "report.xlsx"
    assert sanitize_filename("clean_sales.xlsx") == "clean_sales.xlsx"


def test_escape_for_display() -> None:
    """escape_for_display prevents XSS in UI."""
    payload = "<script>alert('xss')</script>"
    escaped = escape_for_display(payload)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped


def test_rate_limiter() -> None:
    """RateLimiter enforces tokens per window."""
    limiter = RateLimiter(max_tokens=3)
    user = "user-123"
    limiter.reset(user)

    assert limiter.check_and_consume(user, cost=1) is True
    assert limiter.check_and_consume(user, cost=1) is True
    assert limiter.check_and_consume(user, cost=1) is True
    # 4th request in the same window should be rejected
    assert limiter.check_and_consume(user, cost=1) is False
    assert limiter.remaining(user) == 0

    limiter.reset(user)
    assert limiter.remaining(user) == 3


def test_validate_upload_valid_file(test_settings: Settings) -> None:
    """Valid xlsx file passes all security checks."""
    path = SAMPLE_DIR / "sales_en.xlsx"
    with open(path, "rb") as f:
        file_bytes = f.read()

    res = validate_upload(file_bytes, "sales_en.xlsx", "trial", test_settings)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_upload_invalid_extension(test_settings: Settings) -> None:
    """Non-xlsx extension is immediately rejected."""
    res = validate_upload(b"some content", "data.csv", "trial", test_settings)
    assert res.is_valid is False
    assert any(".xlsx" in e for e in res.errors)


def test_validate_upload_fake_magic_bytes(test_settings: Settings) -> None:
    """Text file renamed to .xlsx is rejected due to invalid magic bytes."""
    fake_content = b"Not a zip file at all"
    res = validate_upload(fake_content, "fake.xlsx", "trial", test_settings)
    assert res.is_valid is False
    assert any("header" in e.lower() or "zip" in e.lower() or "corrupt" in e.lower() for e in res.errors)


def test_validate_upload_zip_bomb_rejection(test_settings: Settings) -> None:
    """Files with excessive uncompressed content are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/huge.xml", b"\x00" * (600 * 1024 * 1024))
    file_bytes = buf.getvalue()

    res = validate_upload(file_bytes, "bomb.xlsx", "trial", test_settings)
    assert res.is_valid is False
    assert any("security" in e.lower() or "rejected" in e.lower() or "bomb" in e.lower() for e in res.errors)
