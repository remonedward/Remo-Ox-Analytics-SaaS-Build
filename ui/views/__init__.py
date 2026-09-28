from __future__ import annotations

"""Views package for REMO_OX Analytics following OOP view hierarchy."""

from ui.views.admin_settings_view import AdminSettingsView
from ui.views.auth_view import AuthView
from ui.views.base import BaseView
from ui.views.dashboard_view import DashboardView
from ui.views.export_view import ExportView
from ui.views.mapping_view import MappingView
from ui.views.quality_view import QualityView
from ui.views.reports_view import ReportsView
from ui.views.upload_view import UploadView

__all__ = [
    "AdminSettingsView",
    "AuthView",
    "BaseView",
    "DashboardView",
    "ExportView",
    "MappingView",
    "QualityView",
    "ReportsView",
    "UploadView",
]

