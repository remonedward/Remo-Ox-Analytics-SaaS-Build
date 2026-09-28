from __future__ import annotations

"""Data quality inspection and health report view."""

import pandas as pd

from analytics.schemas import QualityReport
from core.i18n import t
from ui.components.kpi_card import KPICardComponent
from ui.components.table_view import TableViewComponent
from ui.views.base import BaseView


class QualityView(BaseView):
    """View rendering detailed data quality and hygiene metrics."""

    def get_title(self) -> str:
        return "تقرير جودة البيانات" if self.language == "ar" else "Data Quality Report"

    def get_icon(self) -> str:
        return "🩺"

    def render(self) -> None:
        """Render quality report metrics and diagnostics."""
        try:
            import streamlit as st

            user = self.session.get_user()
            active_id = self.session.get_active_dataset_id()
            if not user or not active_id:
                st.warning(t("no_datasets", lang=self.language))
                return

            dataset = self.dataset_service.get_dataset(active_id, user.id)
            if not dataset or not dataset.quality:
                st.info(t("no_data", lang=self.language))
                return

            st.title(f"🩺 {self.get_title()}")
            st.caption(f"الملف: {dataset.display_name}")

            quality_rep = QualityReport.model_validate(dataset.quality)

            # Sheet selector if multiple sheets
            sheet_names = [s.sheet_name for s in quality_rep.sheets]
            if not sheet_names:
                st.info(t("no_data", lang=self.language))
                return

            selected_sheet = sheet_names[0]
            if len(sheet_names) > 1:
                selected_sheet = st.selectbox(
                    "اختر الصفحة لعرض التقرير" if self.language == "ar" else "Select Sheet",
                    options=sheet_names,
                )

            sheet_report = next((s for s in quality_rep.sheets if s.sheet_name == selected_sheet), None)
            if not sheet_report:
                st.info(t("no_data", lang=self.language))
                return

            # KPI Summary
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                KPICardComponent(
                    title="الصفوف الفعلية" if self.language == "ar" else "Data Rows",
                    value=sheet_report.row_count,
                    language=self.language,
                ).render()
            with c2:
                KPICardComponent(
                    title="صفوف مكررة" if self.language == "ar" else "Duplicate Rows",
                    value=sheet_report.duplicate_rows,
                    unit="",
                    is_good_delta=(sheet_report.duplicate_rows == 0),
                    language=self.language,
                ).render()
            with c3:
                KPICardComponent(
                    title="صفوف إجمالية مستبعدة" if self.language == "ar" else "Excluded Totals",
                    value=sheet_report.excluded_total_rows,
                    language=self.language,
                ).render()
            with c4:
                total_outliers = sum(c.outliers_count for c in sheet_report.columns)
                KPICardComponent(
                    title="القيم الشاذة (Outliers)" if self.language == "ar" else "Outliers Count",
                    value=total_outliers,
                    language=self.language,
                ).render()

            st.divider()

            # Warnings list
            if sheet_report.warnings:
                st.subheader("⚠️ التنبيهات والملاحظات" if self.language == "ar" else "⚠️ Warnings & Notes")
                for w in sheet_report.warnings:
                    st.warning(w)

            # Column-by-column breakdown table
            st.subheader("تفصيل جودة الأعمدة" if self.language == "ar" else "Column Quality Breakdown")
            col_rows: list[dict] = []
            for c in sheet_report.columns:
                col_rows.append({
                    "العمود" if self.language == "ar" else "Column": c.column,
                    "النوع" if self.language == "ar" else "DType": c.role or "--",
                    "قيم فارغة" if self.language == "ar" else "Nulls": f"{c.null_count} ({c.null_pct:.1f}%)",
                    "أخطاء قراءة" if self.language == "ar" else "Parse Failures": c.parse_failures,
                    "قيم شاذة" if self.language == "ar" else "Outliers": c.outliers_count,
                    "قيم سالبة" if self.language == "ar" else "Negatives": c.negative_count,
                    "قيم فريدة" if self.language == "ar" else "Unique": c.unique_count,
                })

            TableViewComponent(
                data=pd.DataFrame(col_rows),
                show_download=True,
                language=self.language,
            ).render()

        except Exception:
            pass
