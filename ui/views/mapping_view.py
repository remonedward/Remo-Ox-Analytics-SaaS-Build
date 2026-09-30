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

            current_biz = getattr(dataset, "business_type", "products") or "products"
            biz_options = {
                "products": "🛍️ شركات تجارية وبيع منتجات (بضائع، مبيعات، مخزون)" if self.language == "ar" else "🛍️ Products & Inventory",
                "services": "💼 شركات خدمية واستشارات (خدمات، أتعاب، ساعات عمل)" if self.language == "ar" else "💼 Services & Consulting",
            }
            selected_biz = st.radio(
                "طبيعة نشاط الشركة لهذا الملف / Business Activity" if self.language == "ar" else "Business Model",
                options=list(biz_options.keys()),
                index=0 if current_biz == "products" else 1,
                format_func=lambda x: biz_options[x],
                horizontal=True,
                key="mapping_biz_type",
            )
            is_service_mode = selected_biz == "services"

            if is_service_mode:
                st.info(
                    "💡 **وضع الشركات الخدمية مفعل:** لا حاجة لتحديد أعمدة المخزون (`stock_qty` / `last_movement_date`). "
                    "حدد فقط عمود اسم الخدمة، وساعات العمل أو الجلسات (إن وجدت)، والأتعاب والإيرادات."
                    if self.language == "ar"
                    else "💡 **Services Mode Active:** Inventory columns (`stock_qty`) are not needed. "
                    "Map service name, hours/sessions, and service fees/revenue."
                )

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
                        # Contextual role label
                        if is_service_mode:
                            if role == "product":
                                role_label = "اسم الخدمة / الاستشارة" if self.language == "ar" else "Service / Consultation Name"
                            elif role == "category":
                                role_label = "نوع / قسم الخدمة" if self.language == "ar" else "Service Category"
                            elif role == "quantity":
                                role_label = "ساعات العمل / عدد الجلسات" if self.language == "ar" else "Hours / Sessions"
                            elif role == "unit_price":
                                role_label = "سعر الخدمة / أجر الساعة" if self.language == "ar" else "Hourly Rate / Service Fee"
                            elif role == "revenue":
                                role_label = "إيرادات الخدمات / الأتعاب" if self.language == "ar" else "Service Revenue / Fees"
                            elif role == "unit_cost":
                                role_label = "تكلفة الخدمة المباشرة" if self.language == "ar" else "Direct Service Cost"
                            elif role in ("stock_qty", "last_movement_date"):
                                role_label = "المخزون (غير منطبق للشركات الخدمية)" if self.language == "ar" else "Inventory (N/A for Services)"
                            else:
                                role_label = t(f"mapping_role_{role}", lang=self.language)
                        else:
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
                    ok = self.dataset_service.update_mapping(
                        dataset.id,
                        user.id,
                        new_mapping,
                        business_type=selected_biz,
                    )
                    if ok:
                        st.success(t("success", lang=self.language))
                        self.session.set_current_view("dashboard")
                        st.rerun()
                    else:
                        st.error(t("error_generic", lang=self.language))

        except Exception:
            pass
