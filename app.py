from __future__ import annotations

"""Main application entry point for REMO_OX Analytics.

Orchestrates services, views, session state, and theming following
strict Object-Oriented Programming (OOP) patterns.
"""


from ai.orchestrator import AIOrchestrator
from core.config import Settings, get_settings
from core.logging_setup import get_logger, setup_logging
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from storage import get_storage_backend
from storage.base import StorageBackend
from ui.navigation import NavigationManager
from ui.session import SessionManager
from ui.theme import ThemeManager
from ui.views.admin_settings_view import AdminSettingsView
from ui.views.auth_view import AuthView
from ui.views.chat_view import ChatView
from ui.views.dashboard_view import DashboardView
from ui.views.export_view import ExportView
from ui.views.mapping_view import MappingView
from ui.views.quality_view import QualityView
from ui.views.reports_view import ReportsView
from ui.views.upload_view import UploadView

logger = get_logger(__name__)


class Application:
    """Root Application coordinator for REMO_OX Analytics."""

    def __init__(
        self,
        settings: Settings | None = None,
        backend: StorageBackend | None = None,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        self.backend: StorageBackend = backend or get_storage_backend(self.settings)

        # UI & Session Coordinators
        self.session: SessionManager = SessionManager(
            default_language=self.settings.default_language
        )
        self.theme: ThemeManager = ThemeManager(settings=self.settings)

        # Core Services
        self.auth_service: AuthService = AuthService(
            backend=self.backend,
            settings=self.settings,
        )
        self.dataset_service: DatasetService = DatasetService(
            backend=self.backend,
            settings=self.settings,
        )
        self.export_service: ExportService = ExportService(
            backend=self.backend,
            settings=self.settings,
        )
        self.ai_orchestrator: AIOrchestrator = AIOrchestrator(
            backend=self.backend,
            settings=self.settings,
        )

        # Navigation Manager & View Registry
        self.nav: NavigationManager = NavigationManager(
            session=self.session,
            dataset_service=self.dataset_service,
            auth_service=self.auth_service,
            settings=self.settings,
        )

        # Views
        self.auth_view: AuthView = AuthView(
            session=self.session,
            dataset_service=self.dataset_service,
            auth_service=self.auth_service,
            settings=self.settings,
        )

        self._register_views()

    def _register_views(self) -> None:
        """Register application views into the navigation router."""
        self.nav.register_view(
            "dashboard",
            DashboardView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "reports",
            ReportsView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                export_service=self.export_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "chat",
            ChatView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                orchestrator=self.ai_orchestrator,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "upload",
            UploadView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "mapping",
            MappingView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "quality",
            QualityView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "exports",
            ExportView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                export_service=self.export_service,
                settings=self.settings,
            ),
        )
        self.nav.register_view(
            "admin_settings",
            AdminSettingsView(
                session=self.session,
                dataset_service=self.dataset_service,
                auth_service=self.auth_service,
                orchestrator=self.ai_orchestrator,
                settings=self.settings,
            ),
        )

    def run(self) -> None:
        """Execute main application loop."""
        # Apply active theme & RTL stylesheet
        lang = self.session.get_language()
        self.theme.apply(lang)

        # Authenticated Gate
        if not self.session.is_authenticated():
            self.auth_view.render()
        else:
            self.nav.render_sidebar()
            self.nav.render_active_view()


def main() -> None:
    """Streamlit entry point."""
    try:
        import streamlit as st

        # Streamlit requires set_page_config to be the very first Streamlit call
        st.set_page_config(
            page_title="REMO_OX Analytics",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        pass

    setup_logging()
    app = Application()
    logger.info("REMO_OX Analytics started successfully. UI is ready.")
    app.run()


if __name__ == "__main__":
    main()
