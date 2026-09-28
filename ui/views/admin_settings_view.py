from __future__ import annotations

"""Admin and LLM Provider Settings View for REMO_OX Analytics.

Provides dedicated administrative controls for:
1. LLM Model configuration (Google Gemini, OpenAI, Groq, Ollama, etc.), API keys, and connection testing.
2. Admin credentials security, password changes, and exclusivity locking.
3. Full database backup snapshot downloads and system audit metrics.
"""

import time
from typing import Any

from ai.orchestrator import AIOrchestrator
from core.config import Settings, get_settings, update_env_file
from core.logging_setup import get_logger
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from ui.session import SessionManager
from ui.views.base import BaseView

logger = get_logger(__name__)


class AdminSettingsView(BaseView):
    """Administrator Settings View following OOP patterns."""

    admin_only: bool = True

    def __init__(
        self,
        session: SessionManager,
        dataset_service: DatasetService,
        auth_service: AuthService,
        orchestrator: AIOrchestrator,
        settings: Settings,
    ) -> None:
        super().__init__(
            session=session,
            dataset_service=dataset_service,
            auth_service=auth_service,
            settings=settings,
        )
        self.orchestrator = orchestrator

    def get_title(self) -> str:
        """Localized view title."""
        return "إعدادات المشرف والذكاء الاصطناعي" if self.language == "ar" else "Admin & AI Settings"

    def get_icon(self) -> str:
        """Icon for navigation."""
        return "⚙️"

    def render(self) -> None:
        """Render the complete admin settings dashboard."""
        try:
            import streamlit as st
        except ImportError:
            return

        user = self.session.get_user()
        if not user or not user.is_admin:
            st.error(
                "⛔ ليس لديك صلاحية المشرف للوصول إلى هذه الصفحة."
                if self.language == "ar"
                else "⛔ Unauthorized. Admin privileges required."
            )
            return

        # Header
        st.title(f"{self.get_icon()} {self.get_title()}")
        st.caption(
            "إدارة مزود خدمة نماذج الذكاء الاصطناعي، أمان وبيانات المشرف، والنسخ الاحتياطي لقاعدة البيانات."
            if self.language == "ar"
            else "Configure LLM providers, manage admin security, and export complete database backups."
        )

        tab_llm, tab_admin, tab_db = st.tabs(
            [
                "🤖 مزود خدمة الذكاء الاصطناعي (LLM)"
                if self.language == "ar"
                else "🤖 LLM Provider",
                "👑 أمان وبيانات المشرف"
                if self.language == "ar"
                else "👑 Admin Credentials",
                "📦 قاعدة البيانات والنسخ الاحتياطي"
                if self.language == "ar"
                else "📦 Database & Backups",
            ]
        )

        with tab_llm:
            self._render_llm_tab()

        with tab_admin:
            self._render_admin_tab()

        with tab_db:
            self._render_database_tab()

    # -----------------------------------------------------------------------
    # Tab 1: LLM Provider Configuration
    # -----------------------------------------------------------------------

    def _render_llm_tab(self) -> None:
        """Render LLM provider selection, API key input, and connection testing."""
        import streamlit as st

        is_ar = self.language == "ar"

        st.subheader("🤖 " + ("إعدادات مزود خدمة الذكاء الاصطناعي" if is_ar else "LLM Provider Configuration"))

        # Info callout about Google Gemini recommendation
        if is_ar:
            st.info(
                "💡 **النموذج الافتراضي الموصى به:** `Google Gemini 2.0 Flash` — أحدث نماذج جوجل، فائق السرعة، "
                "ذو قدرات تحليلية متقدمة وبتكلفة منخفضة جداً. يمكنك أيضاً اختيار أي نموذج من OpenAI أو Anthropic أو Groq أو DeepSeek أو إدخال نموذج مخصص."
            )
        else:
            st.info(
                "💡 **Recommended Default Model:** `Google Gemini 2.0 Flash` — ultra-fast, high intelligence, and lowest cost. "
                "You can also use models from OpenAI, Anthropic, Groq, DeepSeek, Ollama, or enter any custom LiteLLM model identifier."
            )

        model_presets = {
            "gemini/gemini-2.0-flash": "Google Gemini 2.0 Flash (موصى به - حديث ومنخفض التكلفة)" if is_ar else "Google Gemini 2.0 Flash (Recommended)",
            "gemini/gemini-1.5-flash": "Google Gemini 1.5 Flash (سريع وخفيف)" if is_ar else "Google Gemini 1.5 Flash (Fast & lightweight)",
            "gemini/gemini-1.5-pro": "Google Gemini 1.5 Pro (تحليل متقدم للمهام المعقدة)" if is_ar else "Google Gemini 1.5 Pro (Deep reasoning)",
            "openai/gpt-4o-mini": "OpenAI GPT-4o-mini (اقتصادي من OpenAI)" if is_ar else "OpenAI GPT-4o-mini",
            "openai/gpt-4o": "OpenAI GPT-4o (النموذج الرائد من OpenAI)" if is_ar else "OpenAI GPT-4o",
            "anthropic/claude-3-5-haiku-20241022": "Anthropic Claude 3.5 Haiku",
            "groq/llama-3.3-70b-versatile": "Groq Llama 3.3 70B (سرعة فائقة)" if is_ar else "Groq Llama 3.3 70B (Ultra-fast)",
            "deepseek/deepseek-chat": "DeepSeek Chat (V3)",
            "ollama/llama3.2": "Ollama (محلي بدون إنترنت)" if is_ar else "Ollama (Local / Offline)",
            "custom": "نموذج مخصص / Custom Model String..." if is_ar else "Custom Model String...",
        }

        current_model = self.settings.llm_model.strip()
        current_preset = current_model if current_model in model_presets else "custom"

        col_preset, col_custom = st.columns([1, 1])
        with col_preset:
            selected_preset = st.selectbox(
                "اختر النموذج أو مزود الخدمة" if is_ar else "Select Model or Provider",
                options=list(model_presets.keys()),
                index=list(model_presets.keys()).index(current_preset),
                format_func=lambda k: model_presets.get(k, k),
                key="admin_llm_preset_select",
            )

        with col_custom:
            if selected_preset == "custom":
                chosen_model = st.text_input(
                    "معرّف النموذج المخصص (LiteLLM)" if is_ar else "Custom Model Identifier (LiteLLM)",
                    value=current_model if current_model not in model_presets else "",
                    placeholder="e.g. gemini/gemini-2.0-flash, mistral/mistral-large, etc.",
                    key="admin_llm_custom_input",
                ).strip()
            else:
                chosen_model = selected_preset
                st.text_input(
                    "معرّف النموذج النشط" if is_ar else "Active Model String",
                    value=chosen_model,
                    disabled=True,
                    key="admin_llm_model_display",
                )

        # API Key Input
        current_has_key = bool(self.settings.llm_api_key.get_secret_value().strip())
        key_placeholder = (
            "•••••••• (مفتاح محفوظ حالياً)" if current_has_key else "أدخل مفتاح API الخاص بالنموذج"
            if is_ar
            else "•••••••• (Key currently configured)" if current_has_key else "Enter provider API key"
        )

        api_key_input = st.text_input(
            "مفتاح الربط (API Key)" if is_ar else "API Key",
            type="password",
            placeholder=key_placeholder,
            help="مفتاح API الخاص بمزود الخدمة (مثل Google AI Studio API Key أو OpenAI API Key). يتم تشفيره ولا يظهر للمستخدمين نهائياً."
            if is_ar
            else "API key for the LLM provider (e.g. Google AI Studio Key, OpenAI Key). Stored securely and never exposed to users.",
            key="admin_llm_api_key_input",
        ).strip()

        # Advanced Settings Expander
        with st.expander("⚙️ " + ("إعدادات متقدمة للنموذج (اختياري)" if is_ar else "Advanced Model Parameters (Optional)")):
            col_t, col_tok = st.columns([1, 1])
            with col_t:
                temperature = st.slider(
                    "درجة التنوع والابتكار (Temperature)" if is_ar else "Temperature",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(self.settings.llm_temperature),
                    step=0.05,
                    help="القيمة المنخفضة (0.2) موصى بها للحسابات والتقارير المالية الدقيقة."
                    if is_ar
                    else "Lower value (0.2) recommended for factual analytics.",
                    key="admin_llm_temp",
                )
            with col_tok:
                max_tokens = st.number_input(
                    "الحد الأقصى للرموز (Max Tokens)" if is_ar else "Max Output Tokens",
                    min_value=200,
                    max_value=8000,
                    value=int(self.settings.llm_max_tokens),
                    step=100,
                    key="admin_llm_tokens",
                )

            api_base = st.text_input(
                "عنوان نقطة النهاية المخصصة (API Base URL) - اختياري"
                if is_ar
                else "Custom API Base URL (Optional)",
                value=self.settings.llm_api_base or "",
                placeholder="e.g. http://localhost:11434 for Ollama or Azure Endpoint",
                key="admin_llm_api_base",
            ).strip()

            col_fb_m, col_fb_k = st.columns([1, 1])
            with col_fb_m:
                fallback_model = st.text_input(
                    "نموذج احتياطي للطوارئ (Fallback Model) - اختياري"
                    if is_ar
                    else "Fallback Model (Optional)",
                    value=self.settings.llm_fallback_model or "",
                    placeholder="e.g. groq/llama-3.1-8b-instant",
                    key="admin_llm_fb_model",
                ).strip()
            with col_fb_k:
                fallback_key = st.text_input(
                    "مفتاح النموذج الاحتياطي (Fallback API Key) - اختياري"
                    if is_ar
                    else "Fallback API Key (Optional)",
                    type="password",
                    value="",
                    placeholder="••••••••" if self.settings.llm_fallback_api_key.get_secret_value() else "",
                    key="admin_llm_fb_key",
                ).strip()

        st.divider()

        # Action Buttons: Test Connection & Save
        col_test, col_save = st.columns([1, 1])

        with col_test:
            if st.button("🧪 " + ("اختبار الاتصال بالنموذج" if is_ar else "Test Connection"), use_container_width=True):
                # Resolve key to test
                key_to_test = api_key_input or self.settings.llm_api_key.get_secret_value()
                model_to_test = chosen_model or self.settings.llm_model

                if not model_to_test:
                    st.error("يرجى تحديد اسم النموذج أولاً." if is_ar else "Please specify a model.")
                elif not key_to_test and not selected_preset.startswith("ollama"):
                    st.error("يرجى إدخال مفتاح API لإجراء الاختبار." if is_ar else "Please provide an API key to test.")
                else:
                    with st.spinner("جارٍ اختبار الاتصال وإرسال طلب تجريبي إلى النموذج..." if is_ar else "Testing connection to model..."):
                        t0 = time.monotonic()
                        test_res = self._test_llm_connection(
                            model=model_to_test,
                            api_key=key_to_test,
                            api_base=api_base or None,
                        )
                        duration = time.monotonic() - t0

                        if test_res.get("success"):
                            st.success(
                                f"✅ **تم الاتصال بنجاح!**\n\n"
                                f"- **النموذج:** `{model_to_test}`\n"
                                f"- **زمن الاستجابة:** `{duration:.2f}` ثانية\n"
                                f"- **استجابة النموذج التجريبية:** *\"{test_res.get('reply')}\"*"
                                if is_ar
                                else f"✅ **Connection successful!**\n\n"
                                f"- **Model:** `{model_to_test}`\n"
                                f"- **Latency:** `{duration:.2f}`s\n"
                                f"- **Sample reply:** *\"{test_res.get('reply')}\"*"
                            )
                        else:
                            st.error(
                                f"❌ **فشل الاتصال بالنموذج:**\n\n`{test_res.get('error')}`"
                                if is_ar
                                else f"❌ **Connection failed:**\n\n`{test_res.get('error')}`"
                            )

        with col_save:
            if st.button("💾 " + ("حفظ وتطبيق الإعدادات" if is_ar else "Save & Apply Settings"), type="primary", use_container_width=True):
                model_to_save = chosen_model or self.settings.llm_model

                updates = {
                    "LLM_MODEL": model_to_save,
                    "LLM_TEMPERATURE": str(temperature),
                    "LLM_MAX_TOKENS": str(max_tokens),
                    "LLM_API_BASE": api_base,
                    "LLM_FALLBACK_MODEL": fallback_model,
                }
                if api_key_input:
                    updates["LLM_API_KEY"] = api_key_input
                if fallback_key:
                    updates["LLM_FALLBACK_API_KEY"] = fallback_key

                update_env_file(updates)

                # Refresh in-memory settings
                new_settings = get_settings()
                self.settings = new_settings
                self.orchestrator.provider.settings = new_settings

                st.success("✅ " + ("تم حفظ الإعدادات بنجاح وتحديثها فورياً في النظام!" if is_ar else "Settings successfully saved and applied!"))
                st.rerun()

    def _test_llm_connection(self, model: str, api_key: str | None, api_base: str | None) -> dict[str, Any]:
        """Perform a quick test completion to verify provider and API key validity."""
        try:
            import litellm

            litellm.suppress_debug_info = True

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": "أهلاً، أجب بكلمة واحدة فقط لتأكيد الاتصال: جاهز",
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 30,
                "timeout": 15.0,
            }
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            resp = litellm.completion(**kwargs)
            reply = resp.choices[0].message.content or "جاهز"
            return {"success": True, "reply": reply.strip()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Tab 2: Admin Security & Exclusivity
    # -----------------------------------------------------------------------

    def _render_admin_tab(self) -> None:
        """Render admin credentials management, exclusivity verification, and password change."""
        import streamlit as st

        is_ar = self.language == "ar"
        user = self.session.get_user()
        if not user:
            return

        st.subheader("👑 " + ("أمان المشرف وبيانات الدخول الثابتة" if is_ar else "Admin Security & Fixed Credentials"))

        # Explanation of admin exclusivity
        if is_ar:
            st.markdown(
                """
                > [!IMPORTANT]
                > **كيف تعمل حماية وحصرية حساب المشرف (Admin Exclusivity):**
                > 1. يتم ربط صلاحية المشرف المطلقة حصرياً بالبريد الإلكتروني المسجل في المتغير `ADMIN_EMAILS`.
                > 2. أي مستخدم آخر يقوم بإنشاء حساب على النظام يحصل تلقائياً على رتبة **مستخدم عادي (User)** وخطة تجريبية محدودة، ولا يمكنه الوصول إلى إعدادات المشرف أو رؤية مفاتيح الربط أو تنزيل قاعدة البيانات.
                > 3. بيانات الدخول مشفرة باستخدام خوارزمية `PBKDF2-HMAC-SHA256` مع Salt فريد لكل مستخدم لمنع أي اختراق.
                """
            )
        else:
            st.markdown(
                """
                > [!IMPORTANT]
                > **How Admin Exclusivity Works:**
                > 1. Full administrator rights are strictly restricted to the emails declared in `ADMIN_EMAILS`.
                > 2. Any other person who signs up automatically receives standard `User` role under a trial quota, and cannot access admin views, secrets, or database exports.
                > 3. Passwords are securely hashed with `PBKDF2-HMAC-SHA256` and unique salt.
                """
            )

        col_info1, col_info2 = st.columns([1, 1])
        with col_info1:
            st.markdown(
                f"**{'البريد الإلكتروني الحالي للمشرف:' if is_ar else 'Current Admin Email:'}**\n\n"
                f"`{user.email}`"
            )
        with col_info2:
            st.markdown(
                f"**{'الرتبة والخطة:' if is_ar else 'Role & Plan:'}**\n\n"
                f"`👑 المشرف (Admin)` • `{user.plan_id.upper()}`"
            )

        st.divider()

        # Update ADMIN_EMAILS
        st.markdown("### 📧 " + ("قائمة البريد الإلكتروني للمشرفين المعتمدين" if is_ar else "Authorized Admin Email Addresses"))
        current_admin_emails = self.settings.admin_emails or user.email
        new_admin_emails = st.text_input(
            "عناوين المشرفين (مفصولة بفواصل)" if is_ar else "Admin Emails (comma-separated)",
            value=current_admin_emails,
            help="أي بريد إلكتروني يطابق هذه القائمة يحصل على صلاحية المشرف الكاملة تلقائياً."
            if is_ar
            else "Any email listed here automatically obtains full admin privileges.",
            key="admin_emails_input",
        ).strip()

        if st.button("💾 " + ("تحديث قائمة المشرفين" if is_ar else "Update Admin Emails"), key="btn_update_admin_emails"):
            if not new_admin_emails:
                st.error("لا يمكن ترك قائمة المشرفين فارغة." if is_ar else "Admin emails list cannot be empty.")
            else:
                update_env_file({"ADMIN_EMAILS": new_admin_emails})
                self.settings = get_settings()
                st.success("✅ " + ("تم تحديث قائمة المشرفين بنجاح." if is_ar else "Admin emails updated successfully."))
                st.rerun()

        st.divider()

        # Change Password Form
        st.markdown("### 🔑 " + ("تغيير كلمة مرور المشرف" if is_ar else "Change Admin Password"))
        col_p1, col_p2 = st.columns([1, 1])
        with col_p1:
            new_pass = st.text_input(
                "كلمة المرور الجديدة (6 أحرف على الأقل)" if is_ar else "New Password (min 6 chars)",
                type="password",
                key="admin_new_pass",
            )
        with col_p2:
            confirm_pass = st.text_input(
                "تأكيد كلمة المرور الجديدة" if is_ar else "Confirm New Password",
                type="password",
                key="admin_confirm_pass",
            )

        if st.button("🔐 " + ("تأكيد تغيير كلمة المرور" if is_ar else "Confirm Password Change"), type="primary", key="btn_change_pw"):
            if not new_pass or len(new_pass) < 6:
                st.error("يجب ألا تقل كلمة المرور عن 6 أحرف." if is_ar else "Password must be at least 6 characters.")
            elif new_pass != confirm_pass:
                st.error("كلمتا المرور غير متطابقتين." if is_ar else "Passwords do not match.")
            else:
                ok, err = self.auth_service.change_password(user.id, new_pass)
                if ok:
                    st.success("✅ " + ("تم تغيير كلمة المرور بنجاح! احتفظ بها في مكان آمن." if is_ar else "Password changed successfully!"))
                else:
                    st.error(f"❌ {err}")

    # -----------------------------------------------------------------------
    # Tab 3: Database & Backup Management
    # -----------------------------------------------------------------------

    def _render_database_tab(self) -> None:
        """Render database status, user counts, and full database dump download."""
        import streamlit as st

        is_ar = self.language == "ar"

        st.subheader("📦 " + ("قاعدة البيانات والنسخ الاحتياطي الكامل" if is_ar else "Database & Full Backup"))

        # Database health & statistics
        all_users = self.auth_service._backend.list_all_users()
        user = self.session.get_user()
        datasets = self.dataset_service.list_datasets(user.id) if user else []

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                label="إجمالي المستخدمين" if is_ar else "Total Users",
                value=len(all_users),
            )
        with col2:
            st.metric(
                label="الملفات المحملة للبيانات" if is_ar else "Uploaded Datasets",
                value=len(datasets),
            )
        with col3:
            db_engine = "SQLite (Local WAL Mode)" if self.settings.is_local_mode else "Supabase (Cloud Postgres)"
            st.metric(
                label="محرك قاعدة البيانات" if is_ar else "Database Engine",
                value=db_engine,
            )

        st.divider()

        # Database Snapshot Export
        st.markdown("### 📥 " + ("تنزيل نسخة احتياطية كاملة من قاعدة البيانات" if is_ar else "Download Full Database Backup"))
        st.caption(
            "يمكنك تنزيل ملف قاعدة البيانات كاملاً بضغطة زر واحدة للاحتفاظ به أو استعادته لاحقاً."
            if is_ar
            else "Export and download a complete database snapshot for safekeeping or migrations."
        )

        dump = self.auth_service.export_database_dump()
        size_kb = max(1, dump.size_bytes // 1024)

        st.download_button(
            label=f"⬇️ {('تنزيل ملف قاعدة البيانات الكامل' if is_ar else 'Download Full Database Dump')} ({size_kb} KB)",
            data=dump.data,
            file_name=dump.filename,
            mime=dump.content_type,
            type="primary",
            use_container_width=True,
            key="btn_download_db_dump",
        )

        st.divider()

        # Audit errors expander
        with st.expander("🔍 " + ("سجل أخطاء النظام الأخيرة (Audit Log)" if is_ar else "Recent System Error Logs")):
            errors = self.auth_service._backend.list_recent_errors(limit=20)
            if not errors:
                st.info("لا توجد أخطاء مسجلة في النظام. كل شيء يعمل بشكل سليم." if is_ar else "No logged errors. All systems healthy.")
            else:
                for err in errors:
                    st.code(
                        f"[{err.get('created_at')}] Location: {err.get('location')}\nMessage: {err.get('message')}"
                    )
