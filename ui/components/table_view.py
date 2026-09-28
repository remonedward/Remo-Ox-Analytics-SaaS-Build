from __future__ import annotations

"""Table View UI component."""


import pandas as pd

from analytics.schemas import ToolResult
from core.i18n import t
from ui.components.base import BaseComponent


class TableViewComponent(BaseComponent):
    """Component for rendering structured tabular data with pagination and export."""

    def __init__(
        self,
        data: pd.DataFrame | ToolResult | list[dict],
        title: str = "",
        max_rows: int = 50,
        show_download: bool = True,
        notes: list[str] | None = None,
        calculation_description: str = "",
        language: str = "ar",
    ) -> None:
        self.title = title
        self.max_rows = max_rows
        self.show_download = show_download
        self.notes = notes or []
        self.calculation_description = calculation_description
        self.language = language

        # Normalize data to pd.DataFrame
        if isinstance(data, pd.DataFrame):
            self.df = data
            self.truncated = len(data) > max_rows
            self.total_rows = len(data)
        elif isinstance(data, ToolResult):
            self.df = pd.DataFrame(data.data) if data.data else pd.DataFrame(columns=data.columns)
            self.truncated = data.truncated
            self.total_rows = data.total_rows
            if not self.notes:
                self.notes = data.notes
            if not self.calculation_description:
                self.calculation_description = data.calculation_description
        else:
            self.df = pd.DataFrame(data)
            self.truncated = len(self.df) > max_rows
            self.total_rows = len(self.df)

    def render(self) -> None:
        """Render table component to Streamlit."""
        try:
            import streamlit as st

            if self.title:
                st.subheader(self.title)

            if self.df.empty:
                st.info(t("no_data", lang=self.language))
                return

            display_df = self.df.head(self.max_rows)
            st.dataframe(display_df, use_container_width=True)

            # Metadata info / Truncation note
            if self.truncated:
                msg = (
                    f"تم عرض أول {len(display_df)} سجل من أصل {self.total_rows} سجل"
                    if self.language == "ar"
                    else f"Showing top {len(display_df)} of {self.total_rows} rows"
                )
                st.caption(f"ℹ️ {msg}")

            # CSV Download Button
            if self.show_download and not self.df.empty:
                csv_bytes = self.df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 " + ("تصدير CSV" if self.language == "ar" else "Export CSV"),
                    data=csv_bytes,
                    file_name="table_export.csv",
                    mime="text/csv",
                    key=f"dl_{id(self)}",
                )

            # Calculation details expander
            if self.calculation_description:
                with st.expander(t("show_calculation", lang=self.language)):
                    st.write(self.calculation_description)

            # Operational notes
            if self.notes:
                for note in self.notes:
                    st.warning(note)

        except Exception:
            pass
