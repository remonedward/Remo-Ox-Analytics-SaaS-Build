from __future__ import annotations

"""Ready-made business analytics reports view."""

from typing import Any

from analytics.charts import ChartRenderer
from analytics.reports import (
    expense_breakdown,
    receivables_aging,
    sales_overview,
    slow_inventory,
    top_products,
)
from analytics.schemas import ReportResult
from core.config import Settings
from core.i18n import t
from core.logging_setup import get_logger
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from ui.components.kpi_card import KPICardComponent
from ui.components.table_view import TableViewComponent
from ui.session import SessionManager
from ui.views.base import BaseView

logger = get_logger(__name__)

REPORT_DEFINITIONS = [
    ("sales_overview", "report_sales_overview", "📈"),
    ("top_products", "report_top_products", "🏆"),
    ("slow_inventory", "report_slow_inventory", "📦"),
    ("receivables_aging", "report_receivables_aging", "⏳"),
    ("expense_breakdown", "report_expense_breakdown", "💸"),
]


class ReportsView(BaseView):
    """View executing and presenting ready-made business intelligence reports."""

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
        self.chart_renderer = ChartRenderer(
            primary_color=settings.brand_primary_color
        )

    def get_title(self) -> str:
        return t("reports_title", lang=self.language)

    def get_icon(self) -> str:
        return "📑"

    def render(self) -> None:
        """Render reports interface and execution results."""
        try:
            import streamlit as st

            user = self.session.get_user()
            active_id = self.session.get_active_dataset_id()
            if not user or not active_id:
                st.warning(t("no_datasets", lang=self.language))
                return

            dataset = self.dataset_service.get_dataset(active_id, user.id)
            if not dataset:
                st.warning(t("no_datasets", lang=self.language))
                return

            ctx = self.dataset_service.load_dataset_context(dataset.id, user.id)
            if not ctx:
                st.error(t("error_generic", lang=self.language))
                return

            # Header
            col_t, col_rep = st.columns([2, 3])
            with col_t:
                st.title(f"📑 {self.get_title()}")
                st.caption(f"الملف: {dataset.display_name}")

            with col_rep:
                # Report Selector
                selected_report_id = st.selectbox(
                    label="Select Report",
                    options=[r[0] for r in REPORT_DEFINITIONS],
                    format_func=lambda rid: next(f"{r[2]} {t(r[1], lang=self.language)}" for r in REPORT_DEFINITIONS if r[0] == rid),
                    label_visibility="collapsed",
                    key="report_selector",
                )

            st.divider()

            # Execute Selected Report
            report_result = self._execute_report(ctx, selected_report_id)
            if not report_result:
                st.info(t("no_data", lang=self.language))
                return

            # Check if all required roles are mapped
            if not report_result.is_available:
                self._render_missing_roles_warning(report_result)
                return

            # Render KPI Summary Cards
            if report_result.kpi_cards:
                cols = st.columns(len(report_result.kpi_cards))
                for idx, card in enumerate(report_result.kpi_cards):
                    with cols[idx]:
                        card_title = card.label_ar if self.language == "ar" else card.label
                        KPICardComponent(
                            title=card_title,
                            value=card.value,
                            unit=card.unit,
                            delta=card.delta,
                            delta_label=card.delta_label,
                            is_good_delta=card.is_good_delta,
                            language=self.language,
                        ).render()

                st.divider()

            # Render Chart if available
            chart_bytes: bytes | None = None
            chart_bytes = self._render_chart_for_report(selected_report_id, report_result)

            # Export PDF Action
            _, col_pdf = st.columns([3, 1])
            with col_pdf:
                if st.button("📄 " + t("export_pdf", lang=self.language), key=f"btn_pdf_{selected_report_id}", use_container_width=True):
                    with st.spinner(t("loading", lang=self.language)):
                        ok, pdf_data, err_pdf = self.export_service.generate_report_pdf(
                            user_id=user.id,
                            report_result=report_result,
                            language=self.language,
                            chart_png_bytes=chart_bytes,
                        )
                        if ok and pdf_data:
                            st.download_button(
                                label="⬇️ " + ("تنزيل التقرير" if self.language == "ar" else "Download PDF"),
                                data=pdf_data,
                                file_name=f"{selected_report_id}_{dataset.display_name}.pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{selected_report_id}",
                            )
                        else:
                            st.error(err_pdf or t("error_generic", lang=self.language))

            # Render Data Tables
            if report_result.tables:
                st.subheader("جدول البيانات التفصيلي" if self.language == "ar" else "Detailed Data Table")
                for table_title, tool_res in report_result.tables.items():
                    TableViewComponent(
                        data=tool_res,
                        title=table_title,
                        max_rows=25,
                        show_download=True,
                        language=self.language,
                    ).render()

            # Calculation Description Expander
            if report_result.calculation_description:
                with st.expander("ℹ️ " + t("show_calculation", lang=self.language)):
                    st.write(report_result.calculation_description)

        except Exception as exc:
            logger.error("Error in ReportsView: %s", exc, exc_info=True)

    def _execute_report(self, ctx: Any, report_id: str) -> ReportResult | None:
        """Dispatch report execution to pure deterministic engine functions."""
        try:
            match report_id:
                case "sales_overview":
                    return sales_overview(ctx)
                case "top_products":
                    return top_products(ctx)
                case "slow_inventory":
                    return slow_inventory(ctx, params={"slow_days_threshold": 90})
                case "receivables_aging":
                    return receivables_aging(ctx)
                case "expense_breakdown":
                    return expense_breakdown(ctx)
                case _:
                    return None
        except Exception as exc:
            logger.warning("Report execution exception for %s: %s", report_id, exc)
            return None

    def _render_chart_for_report(
        self,
        report_id: str,
        report_result: ReportResult,
    ) -> bytes | None:
        """Render suitable chart based on report tables and return PNG bytes."""
        try:
            import pandas as pd

            chart_bytes: bytes | None = None

            if report_id == "sales_overview" and "monthly_revenue" in report_result.tables:
                t_res = report_result.tables["monthly_revenue"]
                df = pd.DataFrame(t_res.data)
                if not df.empty and "month" in df.columns and "revenue" in df.columns:
                    title = "اتجاه الإيرادات الشهرية" if self.language == "ar" else "Monthly Revenue Trend"
                    self.chart_renderer.render_to_streamlit("line", df, "month", "revenue", title, self.language)
                    chart_bytes = self.chart_renderer.render_png_bytes("line", df, "month", "revenue", title, self.language)

            elif report_id == "top_products" and "top_products" in report_result.tables:
                t_res = report_result.tables["top_products"]
                df = pd.DataFrame(t_res.data).head(10)
                prod_col = df.columns[0]
                val_col = df.columns[1]
                title = "أفضل 10 منتجات مبيعاً" if self.language == "ar" else "Top 10 Selling Products"
                self.chart_renderer.render_to_streamlit("hbar", df, prod_col, val_col, title, self.language)
                chart_bytes = self.chart_renderer.render_png_bytes("hbar", df, prod_col, val_col, title, self.language)

            elif report_id == "expense_breakdown" and "category_totals" in report_result.tables:
                t_res = report_result.tables["category_totals"]
                df = pd.DataFrame(t_res.data).head(8)
                cat_col = df.columns[0]
                amt_col = df.columns[1]
                title = "توزيع المصروفات حسب الفئة" if self.language == "ar" else "Expense Distribution by Category"
                self.chart_renderer.render_to_streamlit("pie", df, cat_col, amt_col, title, self.language)
                chart_bytes = self.chart_renderer.render_png_bytes("pie", df, cat_col, amt_col, title, self.language)

            return chart_bytes
        except Exception as exc:
            logger.warning("Could not render chart: %s", exc)
            return None

    def _render_missing_roles_warning(self, report_result: ReportResult) -> None:
        """Render missing columns warning with direct mapping navigation button."""
        import streamlit as st

        missing_names = [t(f"mapping_role_{r}", lang=self.language) for r in report_result.missing_roles]
        roles_text = "، ".join(missing_names)

        st.warning(t("report_missing_roles", lang=self.language, roles=roles_text))
        if st.button("🏷️ " + t("mapping_title", lang=self.language), type="primary"):
            self.session.set_current_view("mapping")
            st.rerun()
