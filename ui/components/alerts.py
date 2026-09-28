from __future__ import annotations

"""Alert and Notification UI Component."""

from ui.components.base import BaseComponent


class AlertComponent(BaseComponent):
    """Component for localized, consistent alerts."""

    def __init__(self, message: str, level: str = "info") -> None:
        self.message = message
        self.level = level

    def render(self) -> None:
        """Render alert to active Streamlit container."""
        try:
            import streamlit as st

            match self.level:
                case "error":
                    st.error(self.message)
                case "warning":
                    st.warning(self.message)
                case "success":
                    st.success(self.message)
                case _:
                    st.info(self.message)
        except Exception:
            pass
