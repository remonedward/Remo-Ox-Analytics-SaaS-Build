from __future__ import annotations

"""Navigation and sidebar layout manager following OOP patterns."""

from core.config import Settings
from core.i18n import t
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from ui.session import SessionManager
from ui.views.base import BaseView


class NavigationManager:
    """Manages view registry, sidebar UI, dataset selection, and page routing."""

    def __init__(
        self,
        session: SessionManager,
        dataset_service: DatasetService,
        auth_service: AuthService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._dataset_service = dataset_service
        self._auth_service = auth_service
        self._settings = settings
        self._views: dict[str, BaseView] = {}

    def register_view(self, view_id: str, view: BaseView) -> None:
        """Register a view into the application router."""
        self._views[view_id] = view

    @property
    def language(self) -> str:
        """Current session language."""
        return self._session.get_language()

    def render_sidebar(self) -> None:
        """Render the complete navigation sidebar."""
        try:
            import streamlit as st

            user = self._session.get_user()
            if not user:
                return

            with st.sidebar:
                # App Branding
                st.markdown(f"## 🏢 {self._settings.app_name}")
                st.caption(t("tagline", lang=self.language))
                st.divider()

                # User Profile Card
                role_label = "👑 مشرف" if user.is_admin else "👤 مستخدم"
                if self.language == "en":
                    role_label = "👑 Admin" if user.is_admin else "👤 User"

                st.markdown(
                    f"**{user.email}**\n\n"
                    f"`{role_label}` • `{user.plan_id.upper()}`"
                )
                st.divider()

                # Dataset Selector
                st.markdown("### 📁 " + ("ملف البيانات النشط" if self.language == "ar" else "Active Dataset"))
                datasets = self._dataset_service.list_datasets(user.id)
                if datasets:
                    dataset_options = {d.id: d.display_name for d in datasets}
                    active_id = self._session.get_active_dataset_id()
                    if active_id not in dataset_options:
                        active_id = datasets[0].id
                        self._session.set_active_dataset_id(active_id)

                    col_sel, col_del = st.columns([4, 1])
                    with col_sel:
                        selected_id = st.selectbox(
                            label="Datasets",
                            options=list(dataset_options.keys()),
                            format_func=lambda x: dataset_options.get(x, x),
                            index=list(dataset_options.keys()).index(active_id),
                            label_visibility="collapsed",
                            key="sidebar_dataset_select",
                        )
                    with col_del:
                        if st.button(
                            "🗑️",
                            key="sidebar_del_dataset_btn",
                            help="حذف هذا الملف نهائياً" if self.language == "ar" else "Delete this dataset",
                        ):
                            self._dataset_service.delete_dataset(active_id, user.id)
                            self._session.set_active_dataset_id(None)
                            st.rerun()

                    if selected_id != active_id:
                        self._session.set_active_dataset_id(selected_id)
                        st.rerun()
                else:
                    st.info(t("no_datasets", lang=self.language))

                st.divider()

                # View Navigation
                current_view = self._session.get_current_view()
                st.markdown("### 🧭 " + ("التنقل" if self.language == "ar" else "Navigation"))

                for view_id, view in self._views.items():
                    if getattr(view, "admin_only", False) and not user.is_admin:
                        continue
                    btn_label = f"{view.get_icon()} {view.get_title()}"
                    is_active = (current_view == view_id)
                    btn_type = "primary" if is_active else "secondary"

                    if st.button(
                        btn_label,
                        key=f"nav_{view_id}",
                        use_container_width=True,
                        type=btn_type,
                    ) and current_view != view_id:
                        self._session.set_current_view(view_id)
                        st.rerun()

                st.divider()

                # Language Switcher & Logout
                col_lang, col_logout = st.columns([1, 1])
                with col_lang:
                    curr_lang = self.language
                    target_lang = "en" if curr_lang == "ar" else "ar"
                    lang_btn_text = "English" if curr_lang == "ar" else "العربية"
                    if st.button(f"🌐 {lang_btn_text}", use_container_width=True):
                        self._session.set_language(target_lang)
                        self._auth_service.update_profile(user.id, {"language": target_lang})
                        st.rerun()

                with col_logout:
                    if st.button("🚪 " + t("logout", lang=self.language), use_container_width=True):
                        self._session.clear()
                        st.rerun()

        except Exception:
            pass

    def render_active_view(self) -> None:
        """Route to and render the current active view."""
        current_view_id = self._session.get_current_view()
        view = self._views.get(current_view_id)
        user = self._session.get_user()
        if view and getattr(view, "admin_only", False) and (not user or not user.is_admin):
            self._session.set_current_view("dashboard")
            view = self._views.get("dashboard")

        if not view and self._views:
            # Fallback to first available view
            view_id = next(iter(self._views.keys()))
            self._session.set_current_view(view_id)
            view = self._views[view_id]

        if view:
            view.render()

