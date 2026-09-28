from __future__ import annotations

"""Dashboard and active dataset overview view."""

from core.i18n import t
from ui.components.kpi_card import KPICardComponent
from ui.components.table_view import TableViewComponent
from ui.views.base import BaseView


class DashboardView(BaseView):
    """View presenting active dataset summary and navigation quick actions."""

    def get_title(self) -> str:
        return "لوحة التحكم" if self.language == "ar" else "Dashboard"

    def get_icon(self) -> str:
        return "📊"

    def render(self) -> None:
        """Render dashboard widgets."""
        try:
            import streamlit as st

            user = self.session.get_user()
            if not user:
                return

            datasets = self.dataset_service.list_datasets(user.id)
            if not datasets:
                self._render_empty_state()
                return

            active_id = self.session.get_active_dataset_id()
            if not active_id:
                active_id = datasets[0].id
                self.session.set_active_dataset_id(active_id)

            dataset = self.dataset_service.get_dataset(active_id, user.id)
            if not dataset:
                self._render_empty_state()
                return

            # Header
            col_t, col_btn = st.columns([3, 1])
            with col_t:
                st.title(f"📊 {dataset.display_name}")
                st.caption(
                    f"ملف: {dataset.original_name} | الحجم: {dataset.file_size_bytes // 1024:,} KB"
                    if self.language == "ar"
                    else f"File: {dataset.original_name} | Size: {dataset.file_size_bytes // 1024:,} KB"
                )

            with col_btn:
                if st.button("➕ " + ("رفع ملف جديد" if self.language == "ar" else "Upload New File"), use_container_width=True):
                    self.session.set_current_view("upload")
                    st.rerun()

            st.divider()

            # KPI Summary row
            total_rows = sum(dataset.row_counts.values()) if dataset.row_counts else 0
            sheets_count = len(dataset.sheet_names)
            mapped_roles_count = len(dataset.mapping)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                KPICardComponent(
                    title="عدد الصفحات" if self.language == "ar" else "Total Sheets",
                    value=sheets_count,
                    unit="صفحات" if self.language == "ar" else "sheets",
                    language=self.language,
                ).render()
            with c2:
                KPICardComponent(
                    title="إجمالي الصفوف" if self.language == "ar" else "Total Rows",
                    value=total_rows,
                    unit="صف" if self.language == "ar" else "rows",
                    language=self.language,
                ).render()
            with c3:
                KPICardComponent(
                    title="الأعمدة المحددة" if self.language == "ar" else "Mapped Roles",
                    value=f"{mapped_roles_count} / 16",
                    language=self.language,
                ).render()
            with c4:
                KPICardComponent(
                    title="حالة جودة البيانات" if self.language == "ar" else "Data Quality",
                    value="جاهز" if mapped_roles_count >= 2 else "يحتاج تحديد",
                    language=self.language,
                ).render()

            st.divider()

            # Sheet Tabs & Table Preview
            st.subheader("معاينة صفحات البيانات" if self.language == "ar" else "Sheet Data Preview")
            ctx = self.dataset_service.load_dataset_context(dataset.id, user.id)

            if ctx and ctx.sheets:
                tabs = st.tabs([f"📄 {name}" for name in dataset.sheet_names if name in ctx.sheets])
                for idx, sheet_name in enumerate(dataset.sheet_names):
                    if sheet_name in ctx.sheets:
                        with tabs[idx]:
                            df = ctx.sheets[sheet_name]
                            TableViewComponent(
                                data=df,
                                max_rows=15,
                                show_download=True,
                                language=self.language,
                            ).render()
            else:
                st.info(t("no_data", lang=self.language))

        except Exception:
            pass

    def _render_empty_state(self) -> None:
        """Render welcoming screen when no datasets exist."""
        import streamlit as st

        st.info(t("no_datasets", lang=self.language))
        if st.button("🚀 " + t("upload_title", lang=self.language), type="primary"):
            self.session.set_current_view("upload")
            st.rerun()
