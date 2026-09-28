from __future__ import annotations

"""Export management and database backup view."""

from core.config import Settings
from core.i18n import t
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from ui.components.kpi_card import KPICardComponent
from ui.session import SessionManager
from ui.views.base import BaseView


class ExportView(BaseView):
    """View displaying PDF export quotas, instructions, and admin full database download."""

    def __init__(
        self,
        session: SessionManager,
        dataset_service: DatasetService,
        auth_service: AuthService,
        export_service: ExportService,
        settings: Settings,
    ) -> None:
        super().__init__(session, dataset_service, auth_service, settings)
        self.export_service = export_service

    def get_title(self) -> str:
        return "التصدير والنسخ الاحتياطي" if self.language == "ar" else "Exports & Backups"

    def get_icon(self) -> str:
        return "📦"

    def render(self) -> None:
        """Render export quota details and admin backup export."""
        try:
            import streamlit as st

            user = self.session.get_user()
            if not user:
                return

            st.title(f"📦 {self.get_title()}")
            st.caption(
                "إدارة التقارير المصدّرة والنسخ الاحتياطية"
                if self.language == "ar"
                else "Manage generated PDF reports and system backups"
            )

            st.divider()

            # Quotas Card
            _, used, limit = self.auth_service.check_quota(user.id, "pdf_export")

            c1, c2 = st.columns(2)
            with c1:
                KPICardComponent(
                    title="تقارير PDF المستهلكة هذا الشهر" if self.language == "ar" else "Monthly PDF Exports Used",
                    value=f"{used} / {limit}",
                    language=self.language,
                ).render()
            with c2:
                remaining = max(0, limit - used)
                KPICardComponent(
                    title="الرصيد المتبقي هذا الشهر" if self.language == "ar" else "Remaining Exports",
                    value=remaining,
                    unit="تقرير" if self.language == "ar" else "reports",
                    is_good_delta=remaining > 0,
                    language=self.language,
                ).render()

            st.divider()

            # Quick Report Link
            st.subheader("📄 " + ("تصدير تقرير جديد" if self.language == "ar" else "Export a New Report"))
            st.write(
                "يمكنك تصدير أي تقرير تحليلي من شاشة التقارير الجاهزة مباشرة بصيغة PDF أنيقة."
                if self.language == "ar"
                else "You can export any analytical report directly into branded PDF format from the Reports screen."
            )
            if st.button("📑 " + t("reports_title", lang=self.language), type="primary"):
                self.session.set_current_view("reports")
                st.rerun()

            # Administrator Full Database Backup Section
            if user.is_admin:
                st.divider()
                st.subheader("👑 " + ("لوحة المشرف: النسخة الاحتياطية الشاملة" if self.language == "ar" else "Admin: Full Database Backup"))
                st.info(
                    "بصفتك مشرفاً، يمكنك تنزيل ملف قاعدة البيانات كاملاً كنسخة احتياطية مشفرة بضغطة زر واحدة."
                    if self.language == "ar"
                    else "As an administrator, you can download a complete backup dump of the entire database."
                )

                if st.button("💾 " + ("تجهيز ملف قاعدة البيانات للتحميل" if self.language == "ar" else "Prepare Database Backup"), key="btn_prep_dump"):
                    with st.spinner(t("loading", lang=self.language)):
                        dump = self.auth_service.export_database_dump()
                        st.download_button(
                            label=f"⬇️ {dump.filename} ({dump.size_bytes // 1024:,} KB)",
                            data=dump.data,
                            file_name=dump.filename,
                            mime=dump.content_type,
                            key="btn_download_db_dump",
                        )
                        st.success(t("success", lang=self.language))

        except Exception:
            pass
