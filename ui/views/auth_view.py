from __future__ import annotations

"""Authentication view (Login and Registration)."""

from core.i18n import t
from ui.views.base import BaseView


class AuthView(BaseView):
    """View rendering login, registration, and credential recovery."""

    def get_title(self) -> str:
        return t("login", lang=self.language)

    def get_icon(self) -> str:
        return "🔐"

    def render(self) -> None:
        """Render login and signup tabs."""
        try:
            import streamlit as st

            # Top branding header
            col_brand, col_lang = st.columns([4, 1])
            with col_brand:
                st.title(t("app_title", lang=self.language))
                st.caption(t("tagline", lang=self.language))

            with col_lang:
                curr_lang = self.language
                new_lang = st.selectbox(
                    "🌐 Language / اللغة",
                    options=["ar", "en"],
                    index=0 if curr_lang == "ar" else 1,
                    format_func=lambda x: "العربية" if x == "ar" else "English",
                    key="auth_lang_select",
                )
                if new_lang != curr_lang:
                    self.session.set_language(new_lang)
                    st.rerun()

            st.divider()

            # Center authentication card
            _, col_center, _ = st.columns([1, 2, 1])
            with col_center:
                if self.settings.is_local_mode:
                    st.info(
                        "👑 **أهلاً بك يا مطور ومشرف المشروع!**\n\n"
                        "أنت تعمل حالياً في **وضع التطوير المحلي**. يمكنك الدخول فوراً بكامل صلاحيات المشرف بضغطة زر واحدة أدناه دون الحاجة لكتابة بيانات:"
                        if self.language == "ar"
                        else "👑 **Welcome, Developer & Admin!**\n\n"
                        "You are running in **Local Dev Mode**. Click below to log in instantly with full Admin privileges:"
                    )
                    if st.button(
                        "⚡ الدخول المباشر كـ مشرف ومطور المشروع (Dev Admin Login)",
                        type="primary",
                        use_container_width=True,
                        key="dev_admin_quick_login",
                    ):
                        admin_email = (
                            self.settings.admin_emails_list[0]
                            if self.settings.admin_emails_list
                            else "admin@remox.com"
                        )
                        dev_admin = self.auth_service.get_or_create_dev_admin(admin_email)
                        self.session.set_user(dev_admin)
                        st.rerun()
                    st.write("")

                tab_login, tab_signup = st.tabs([
                    f"🔑 {t('login', lang=self.language)}",
                    f"📝 {t('signup', lang=self.language)}",
                ])

                with tab_login:
                    self._render_login_form()

                with tab_signup:
                    self._render_signup_form()

        except Exception as exc:
            import logging
            import streamlit as st
            logging.getLogger(__name__).error("AuthView render failed: %s", exc, exc_info=True)
            st.error(f"Error loading authentication view: {exc}")

    def _render_login_form(self) -> None:
        """Render login form."""
        import streamlit as st

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input(t("email", lang=self.language), placeholder="name@company.com")
            password = st.text_input(t("password", lang=self.language), type="password")
            submit = st.form_submit_button(t("login", lang=self.language), use_container_width=True)

            st.caption(
                "💡 المشرف: أول حساب تسجله يحصل تلقائياً على كامل صلاحيات المشرف، أو استخدم زر الدخول المباشر بالأعلى."
                if self.language == "ar"
                else "💡 Admin: The first account created automatically receives Admin privileges, or use Quick Login above."
            )

            if submit:
                if not email or not password:
                    st.error(t("error_generic", lang=self.language))
                    return

                ok, user, err = self.auth_service.sign_in(email, password)
                if ok and user:
                    self.session.set_user(user)
                    st.success(t("success", lang=self.language))
                    st.rerun()
                else:
                    st.error(err or t("error_generic", lang=self.language))

    def _render_signup_form(self) -> None:
        """Render signup form."""
        import streamlit as st

        with st.form("signup_form", clear_on_submit=False):
            email = st.text_input(t("email", lang=self.language), placeholder="name@company.com")
            password = st.text_input(t("password", lang=self.language), type="password")
            confirm_pw = st.text_input(
                "تأكيد كلمة المرور" if self.language == "ar" else "Confirm Password",
                type="password",
            )
            submit = st.form_submit_button(t("signup", lang=self.language), use_container_width=True)
            st.caption(
                "💡 بصفتك المشرف: أول حساب تسجله في التطبيق سيتم تعيينه مشرفاً رئيسياً (Admin) تلقائياً."
                if self.language == "ar"
                else "💡 First registered account automatically becomes the Admin."
            )

            if submit:
                if password != confirm_pw:
                    st.error("كلمات المرور غير متطابقة" if self.language == "ar" else "Passwords do not match.")
                    return

                ok, user, err = self.auth_service.sign_up(email, password, language=self.language)
                if ok and user:
                    self.session.set_user(user)
                    st.success(t("success", lang=self.language))
                    st.rerun()
                else:
                    st.error(err or t("error_generic", lang=self.language))
