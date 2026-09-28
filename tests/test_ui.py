from __future__ import annotations

"""Unit tests for UI components, session manager, and application coordinator."""

import pandas as pd

from app import Application
from core.config import Settings
from storage.base import UserSession
from storage.local_backend import LocalBackend
from ui.components.kpi_card import KPICardComponent
from ui.components.table_view import TableViewComponent
from ui.session import SessionManager
from ui.theme import ThemeManager


def test_session_manager() -> None:
    """SessionManager manages typed session state with fallback."""
    mgr = SessionManager(default_language="ar")

    assert mgr.get_language() == "ar"
    assert not mgr.is_authenticated()
    assert mgr.get_user() is None

    # Set user
    user = UserSession(id="u_1", email="test@example.com", language="en")
    mgr.set_user(user)
    assert mgr.is_authenticated()
    assert mgr.get_user().id == "u_1"
    assert mgr.get_language() == "en"

    # Dataset & View selection
    mgr.set_active_dataset_id("ds_abc")
    assert mgr.get_active_dataset_id() == "ds_abc"

    mgr.set_current_view("upload")
    assert mgr.get_current_view() == "upload"

    # Consent
    assert not mgr.has_ai_consent()
    mgr.set_ai_consent(True)
    assert mgr.has_ai_consent()

    # Clear (logout)
    mgr.clear()
    assert not mgr.is_authenticated()
    assert mgr.get_active_dataset_id() is None
    assert mgr.get_current_view() == "dashboard"


def test_theme_manager(test_settings: Settings) -> None:
    """ThemeManager generates custom styling and RTL stylesheets."""
    theme = ThemeManager(test_settings)

    css_ar = theme.get_custom_css("ar")
    assert "direction: rtl" in css_ar
    assert "Tajawal" in css_ar

    css_en = theme.get_custom_css("en")
    assert "Inter" in css_en
    assert "direction: rtl" not in css_en


def test_kpi_card_component() -> None:
    """KPICardComponent formats numeric values and delta badges correctly."""
    # Thousands formatting
    c1 = KPICardComponent(
        title="Revenue",
        value=15000.5,
        unit="EGP",
        delta=12.4,
        delta_label="vs last month",
        is_good_delta=True,
    )
    val_str = c1._format_value()
    assert "15,000.5" in val_str
    assert "EGP" in val_str

    delta_html = c1._render_delta_html()
    assert "positive" in delta_html
    assert "+12.4%" in delta_html

    # Millions formatting
    c2 = KPICardComponent(
        title="Big Revenue",
        value=2_500_000,
        delta=-5.0,
        is_good_delta=False,
    )
    assert "2.50M" in c2._format_value()
    assert "negative" in c2._render_delta_html()


def test_table_view_component() -> None:
    """TableViewComponent normalizes DataFrames and limits display rows."""
    df = pd.DataFrame({"A": range(100), "B": range(100)})
    table = TableViewComponent(data=df, max_rows=20)
    assert table.truncated is True
    assert table.total_rows == 100
    assert len(table.df) == 100


def test_application_coordinator(temp_backend: LocalBackend, test_settings: Settings) -> None:
    """Application coordinator initializes all OOP services and registers views."""
    app = Application(settings=test_settings, backend=temp_backend)

    assert app.session is not None
    assert app.dataset_service is not None
    assert app.auth_service is not None
    assert app.nav is not None
    assert "dashboard" in app.nav._views
    assert "upload" in app.nav._views
    assert "mapping" in app.nav._views
    assert "quality" in app.nav._views

    # Test running without crash in test environment
    app.run()
