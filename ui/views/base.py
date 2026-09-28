from __future__ import annotations

"""Abstract Base View for application screens."""

from abc import ABC, abstractmethod

from core.config import Settings
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from ui.session import SessionManager


class BaseView(ABC):
    """Base class providing injected services and common state to all views."""

    def __init__(
        self,
        session: SessionManager,
        dataset_service: DatasetService,
        auth_service: AuthService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.dataset_service = dataset_service
        self.auth_service = auth_service
        self.settings = settings

    @property
    def language(self) -> str:
        """Current session language ('ar' or 'en')."""
        return self.session.get_language()

    @abstractmethod
    def get_title(self) -> str:
        """Return localized view title."""

    @abstractmethod
    def get_icon(self) -> str:
        """Return icon representing this view."""

    @abstractmethod
    def render(self) -> None:
        """Render view contents."""
