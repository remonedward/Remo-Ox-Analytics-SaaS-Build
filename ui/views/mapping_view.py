from __future__ import annotations

"""Column role mapping and confirmation view."""

from analytics.schemas import ALL_ROLES
from core.i18n import t
from ui.views.base import BaseView


class MappingView(BaseView):
    """View allowing users to verify, adjust, and confirm column role assignments."""

    def get_title(self) -> str:
        return t("mapping_title", lang=self.language)

    def get_icon(self) -> str:
        return "🏷️"

    def render(self) -> None:
        """Render mapping configuration interface."""
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

            st.title(f"🏷️ {t('mapping_title', lang=self.language)}")
            st.write(t("mapping_instructions", lang=self.language))

            ctx = self.dataset_service.load_dataset_context(dataset.id, user.id)
            if not ctx:
                st.error(t("error_generic", lang=self.language))
                return

            # Primary sheet selection
            primary_sheet = dataset.sheet_names[0]
            if len(dataset.sheet_names) > 1:
                primary_sheet = st.selectbox(
                    "اختر الصفحة الرئيسية للتحليل" if self.language == "ar" else "Select Primary Analysis Sheet",
                    options=dataset.sheet_names,
                    index=0,
                )

            available_columns = ["--", *list(ctx.sheets[primary_sheet].columns)]
            current_mapping = dict(dataset.mapping)

            st.divider()

            # Form to submit mapping
            with st.form("mapping_form"):
                new_mapping: dict[str, str] = {}

                # Display roles in 2 columns
                col1, col2 = st.columns(2)

                for idx, role in enumerate(ALL_ROLES):
                    target_col = col1 if idx % 2 == 0 else col2
                    with target_col:
                        role_label = t(f"mapping_role_{role}", lang=self.language)
                        mapped_val = current_mapping.get(role, "--")
                        default_idx = (
                            available_columns.index(mapped_val)
                            if mapped_val in available_columns
                            else 0
                        )

                        selected_col = st.selectbox(
                            label=f"📌 {role_label} (`{role}`)",
                            options=available_columns,
                            index=default_idx,
                            key=f"role_sel_{role}",
                        )

                        if selected_col != "--":
                            new_mapping[role] = selected_col

                st.divider()
                submitted = st.form_submit_button(
                    label="💾 " + t("mapping_confirm", lang=self.language),
                    type="primary",
                    use_container_width=True,
                )

                if submitted:
                    ok = self.dataset_service.update_mapping(dataset.id, user.id, new_mapping)
                    if ok:
                        st.success(t("success", lang=self.language))
                        self.session.set_current_view("dashboard")
                        st.rerun()
                    else:
                        st.error(t("error_generic", lang=self.language))

        except Exception:
            pass
