from __future__ import annotations

"""KPI Card UI component."""

from typing import Any

from ui.components.base import BaseComponent


class KPICardComponent(BaseComponent):
    """Component for rendering high-impact metric cards."""

    def __init__(
        self,
        title: str,
        value: Any,
        unit: str = "",
        delta: float | None = None,
        delta_label: str = "",
        is_good_delta: bool | None = None,
        language: str = "ar",
    ) -> None:
        self.title = title
        self.value = value
        self.unit = unit
        self.delta = delta
        self.delta_label = delta_label
        self.is_good_delta = is_good_delta
        self.language = language

    def _format_value(self) -> str:
        """Format metric value for readable presentation."""
        if isinstance(self.value, (int, float)):
            if abs(self.value) >= 1_000_000:
                formatted = f"{self.value / 1_000_000:,.2f}M"
            elif abs(self.value) >= 1_000:
                formatted = f"{self.value:,.1f}" if isinstance(self.value, float) else f"{self.value:,}"
            else:
                formatted = f"{self.value:,.2f}" if isinstance(self.value, float) else str(self.value)
            return f"{formatted} {self.unit}".strip()
        return f"{self.value} {self.unit}".strip()

    def _render_delta_html(self) -> str:
        """Render delta badge HTML."""
        if self.delta is None:
            return ""

        sign = "+" if self.delta > 0 else ""
        delta_text = f"{sign}{self.delta:,.1f}% {self.delta_label}".strip()

        if self.is_good_delta is True:
            delta_class = "positive"
            arrow = "▲" if self.delta >= 0 else "▼"
        elif self.is_good_delta is False:
            delta_class = "negative"
            arrow = "▼" if self.delta <= 0 else "▲"
        else:
            delta_class = "neutral"
            arrow = "●"

        return f'<div class="kpi-delta {delta_class}">{arrow} {delta_text}</div>'

    def render(self) -> None:
        """Render KPI card to Streamlit container."""
        try:
            import streamlit as st

            val_str = self._format_value()
            delta_html = self._render_delta_html()

            html = f"""
            <div class="kpi-card">
                <div class="kpi-title">{self.title}</div>
                <div class="kpi-value">{val_str}</div>
                {delta_html}
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
        except Exception:
            pass
