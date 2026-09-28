from __future__ import annotations

"""Session state manager for REMO_OX Analytics.

Encapsulates typed access to user session data, active dataset context,
selected view, and locale preferences.
"""

from typing import Any

from core.logging_setup import get_logger
from storage.base import UserSession

logger = get_logger(__name__)

_DEFAULT_VIEW = "dashboard"


class SessionManager:
    """Manages active user session and UI application state."""

    def __init__(self, default_language: str = "ar") -> None:
        self._default_language = default_language
        self._fallback_state: dict[str, Any] = {}
        self.init()

    @property
    def _state(self) -> Any:
        """Access Streamlit session_state or fallback dictionary."""
        try:
            import streamlit as st

            return st.session_state
        except Exception:
            return self._fallback_state

    def init(self) -> None:
        """Initialize required session state variables if not already present."""
        defaults: dict[str, Any] = {
            "user": None,
            "language": self._default_language,
            "active_dataset_id": None,
            "current_view": _DEFAULT_VIEW,
            "consent_ai": False,
        }
        for key, val in defaults.items():
            if key not in self._state:
                self._state[key] = val

    def get_user(self) -> UserSession | None:
        """Get the authenticated user session."""
        return self._state.get("user")

    def set_user(self, user: UserSession | None) -> None:
        """Set the authenticated user session."""
        self._state["user"] = user
        if user and getattr(user, "language", None):
            self.set_language(user.language)

    def is_authenticated(self) -> bool:
        """Check if a valid user is logged in."""
        return self.get_user() is not None

    def get_language(self) -> str:
        """Get current language code ('ar' or 'en')."""
        return self._state.get("language", self._default_language)

    def set_language(self, language: str) -> None:
        """Set active language ('ar' or 'en')."""
        if language in ("ar", "en"):
            self._state["language"] = language

    def get_active_dataset_id(self) -> str | None:
        """Get ID of the currently selected dataset."""
        return self._state.get("active_dataset_id")

    def set_active_dataset_id(self, dataset_id: str | None) -> None:
        """Set active dataset ID."""
        self._state["active_dataset_id"] = dataset_id

    def get_current_view(self) -> str:
        """Get the name of the currently active view."""
        return self._state.get("current_view", _DEFAULT_VIEW)

    def set_current_view(self, view_name: str) -> None:
        """Set the active view."""
        self._state["current_view"] = view_name

    def has_ai_consent(self) -> bool:
        """Check if user consented to LLM data processing."""
        user = self.get_user()
        if user and user.consent_ai_at:
            return True
        return bool(self._state.get("consent_ai", False))

    def set_ai_consent(self, consent: bool) -> None:
        """Set LLM data processing consent."""
        self._state["consent_ai"] = consent

    def get(self, key: str, default: Any = None) -> Any:
        """Get an arbitrary session state value."""
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set an arbitrary session state value."""
        self._state[key] = value

    def clear(self) -> None:
        """Clear user authentication and reset state (logout)."""
        self._state["user"] = None
        self._state["active_dataset_id"] = None
        self._state["current_view"] = _DEFAULT_VIEW
        self._state["consent_ai"] = False
