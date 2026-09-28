from __future__ import annotations

"""Theme and layout styling manager for REMO_OX Analytics.

Injects custom CSS for bilingual Arabic RTL / English LTR support,
responsive cards, custom tables, and brand color styling.
"""

from core.config import Settings
from core.i18n import get_rtl_css


class ThemeManager:
    """Manages application-wide UI theme, styles, and RTL/LTR layout."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_custom_css(self, language: str = "ar") -> str:
        """Generate comprehensive application stylesheet."""
        primary_color = self._settings.brand_primary_color
        raw_rtl = get_rtl_css() if language == "ar" else ""
        rtl_styles = raw_rtl.replace("<style>", "").replace("</style>", "").strip()

        return f"""
        <style>
        /* Base branding variables */
        :root {{
            --primary-color: {primary_color};
            --bg-light: #F8FAFC;
            --border-color: #E2E8F0;
            --text-dark: #1E293B;
            --text-muted: #64748B;
        }}

        /* Typography & layout */
        @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: { "'Tajawal', sans-serif" if language == 'ar' else "'Inter', sans-serif" };
        }}

        {rtl_styles}

        /* Metric / KPI Card Styling */
        .kpi-card {{
            background: #FFFFFF;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            margin-bottom: 1rem;
        }}

        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}

        .kpi-title {{
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }}

        .kpi-value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-dark);
            letter-spacing: -0.02em;
        }}

        .kpi-delta {{
            font-size: 0.8125rem;
            font-weight: 600;
            margin-top: 0.5rem;
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .kpi-delta.positive {{
            color: #059669;
        }}

        .kpi-delta.negative {{
            color: #DC2626;
        }}

        .kpi-delta.neutral {{
            color: var(--text-muted);
        }}

        /* Dataset header badge */
        .dataset-badge {{
            display: inline-block;
            background-color: #EFF6FF;
            color: #1D4ED8;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.625rem;
            border-radius: 9999px;
            margin-bottom: 0.5rem;
        }}

        /* Hide Streamlit default hamburger menu & footer if desired */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        </style>
        """

    def apply(self, language: str = "ar") -> None:
        """Inject CSS styles into active Streamlit page."""
        try:
            import streamlit as st

            css = self.get_custom_css(language)
            st.markdown(css, unsafe_allow_html=True)
        except Exception:
            pass  # Non-streamlit test environment
