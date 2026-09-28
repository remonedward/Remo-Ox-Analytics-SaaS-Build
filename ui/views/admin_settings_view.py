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
from storage.base import PlanRecord
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

        tab_llm, tab_users, tab_admin, tab_db = st.tabs(
            [
                "🤖 مزود خدمة الذكاء الاصطناعي (LLM)"
                if self.language == "ar"
                else "🤖 LLM Provider",
                "👥 سعات المستخدمين والتعاقدات"
                if self.language == "ar"
                else "👥 User Quotas & Contracts",
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

        with tab_users:
            self._render_users_tab()

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
            "gemini/gemini-2.5-flash": "Google Gemini 2.5 Flash (موصى به للاستقرار والإنتاج - سريع ومخفض التكلفة)" if is_ar else "Google Gemini 2.5 Flash (Recommended - stable & fast)",
            "gemini/gemini-3.7-flash": "Google Gemini 3.7 Flash (الأحدث - ذكاء فائق وبرمجة متقدمة)" if is_ar else "Google Gemini 3.7 Flash (Latest - high intelligence)",
            "gemini/gemini-2.5-flash-lite": "Google Gemini 2.5 Flash-Lite (الأقل تكلفة وخفيف)" if is_ar else "Google Gemini 2.5 Flash-Lite (Ultra low cost)",
            "gemini/gemini-2.5-pro": "Google Gemini 2.5 Pro (تحليل متقدم للمهام المعقدة)" if is_ar else "Google Gemini 2.5 Pro (Deep reasoning)",
            "gemini/gemini-1.5-flash": "Google Gemini 1.5 Flash (سريع ومتوافق)" if is_ar else "Google Gemini 1.5 Flash (Fast fallback)",
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
                "timeout": 25.0,
                "num_retries": 3,
            }
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            resp = litellm.completion(**kwargs)
            reply = resp.choices[0].message.content or "جاهز"
            return {"success": True, "reply": reply.strip()}
        except Exception as exc:
            err_str = str(exc)
            if "503" in err_str or "high demand" in err_str.lower() or "unavailable" in err_str.lower():
                return {
                    "success": False,
                    "error": (
                        "⚠️ خوادم جوجل لهذا النموذج تواجه ضغطاً وطلباً عالياً مؤقتاً (503 High Demand). "
                        "هذا الضغط طبيعي ومؤقت ويزول عادة في ثوانٍ معدودة. أعد المحاولة بعد لحظات، "
                        "أو يمكنك تعيين نموذج احتياطي مثل 'gemini/gemini-2.0-flash' ليعمل تلقائياً عند انشغال النموذج الأساسي."
                        if self.language == "ar"
                        else "⚠️ Google's servers for this model are experiencing temporary high demand (503). "
                        "Spikes are usually short-lived. Please try again in a few moments, "
                        "or configure a fallback model like 'gemini/gemini-2.0-flash'."
                    ),
                }
            return {"success": False, "error": err_str}

    # -----------------------------------------------------------------------
    # Tab 2: User Capacities & Contract Management
    # -----------------------------------------------------------------------

    def _render_users_tab(self) -> None:
        """Render client quota, plan management, and custom contract tier assignment."""
        import pandas as pd
        import streamlit as st

        is_ar = self.language == "ar"

        st.subheader("👥 " + ("إدارة سعات المستخدمين وعقود الاشتراك" if is_ar else "User Capacities & Contract Management"))

        if is_ar:
            st.info(
                "💡 **التحكم في سعات العملاء:** يمكنك هنا تحديد وترقية سعة كل عميل مسجل وفقاً لتعاقده معك "
                "(عدد رسائل الذكاء الاصطناعي الشهرية، عدد ملفات البيانات المسموح برفعها، أقصى حجم للملف، وتقارير PDF). "
                "كما يمكنك إنشاء باقات تعاقدية خاصة وتجميد أو تنشيط الحسابات في أي وقت."
            )
        else:
            st.info(
                "💡 **Client Quota Control:** Configure and upgrade limits for each registered user based on their contract "
                "(Monthly AI messages, allowed datasets, max upload MB, and PDF exports). "
                "You can also create custom contractual tiers and activate/suspend user accounts."
            )

        all_users = self.auth_service.list_all_users()
        all_plans = self.auth_service.list_plans()
        plan_dict = {p.id: p for p in all_plans}

        if not all_users:
            st.warning("لا يوجد مستخدمون مسجلون حالياً." if is_ar else "No users registered yet.")
            return

        # Users overview table
        st.markdown("### 📋 " + ("قائمة المستخدمين والحصص الحالية" if is_ar else "Registered Users & Current Tiers"))

        user_rows = []
        for u in all_users:
            p = plan_dict.get(u.plan_id)
            plan_name = p.name if p else u.plan_id
            limit_ai = p.monthly_ai_messages if p else "N/A"
            limit_ds = p.max_datasets if p else "N/A"
            status_badge = "🟢 نشط" if u.is_active else "🔴 موقوف"
            if not is_ar:
                status_badge = "🟢 Active" if u.is_active else "🔴 Suspended"

            user_rows.append({
                ("البريد الإلكتروني" if is_ar else "Email"): u.email,
                ("الرتبة" if is_ar else "Role"): "👑 مشرف" if u.is_admin else "👤 مستخدم",
                ("الخطة الحالية" if is_ar else "Current Plan"): plan_name,
                ("رسائل الذكاء/شهر" if is_ar else "AI Messages/mo"): limit_ai,
                ("أقصى ملفات" if is_ar else "Max Datasets"): limit_ds,
                ("الحالة" if is_ar else "Status"): status_badge,
            })

        st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)

        st.divider()

        # Update specific user form
        st.markdown("### ✏️ " + ("تعديل وتحديد سعة عميل معين" if is_ar else "Assign / Upgrade Client Capacity"))

        col_u, col_p = st.columns([1, 1])
        with col_u:
            user_options = {u.id: f"{u.email} ({u.plan_id.upper()})" for u in all_users}
            selected_uid = st.selectbox(
                "اختر العميل" if is_ar else "Select Client",
                options=list(user_options.keys()),
                format_func=lambda uid: user_options.get(uid, uid),
                key="admin_user_select",
            )
            target_user = next((u for u in all_users if u.id == selected_uid), all_users[0])

        with col_p:
            plan_options = {
                p.id: f"{p.name} ({p.monthly_ai_messages} رسائل AI • {p.max_datasets} ملفات • {p.max_file_mb}MB)"
                for p in all_plans
            }
            current_pid = target_user.plan_id if target_user.plan_id in plan_options else (all_plans[0].id if all_plans else "trial")
            selected_pid = st.selectbox(
                "اختر الخطة أو السعة المطلوبة" if is_ar else "Select Plan / Quota Tier",
                options=list(plan_options.keys()),
                index=list(plan_options.keys()).index(current_pid) if current_pid in plan_options else 0,
                format_func=lambda pid: plan_options.get(pid, pid),
                key="admin_plan_select",
            )

        col_act, col_btn = st.columns([1, 1])
        with col_act:
            is_active_input = st.checkbox(
                "الحساب مفعل (إلغاء التحديد لتجميد الحساب)" if is_ar else "Account Active (Uncheck to suspend)",
                value=target_user.is_active,
                key=f"user_active_{target_user.id}",
            )

        with col_btn:
            if st.button("💾 " + ("تحديث سعة واشتراك العميل" if is_ar else "Update Client Quota & Plan"), type="primary", use_container_width=True):
                self.auth_service.update_user_plan(target_user.id, selected_pid)
                self.auth_service.update_profile(target_user.id, {"is_active": is_active_input})
                st.success(
                    f"✅ تم تحديث سعة العميل `{target_user.email}` بنجاح!"
                    if is_ar
                    else f"✅ Quota for `{target_user.email}` updated successfully!"
                )
                st.rerun()

        st.divider()

        # Custom plan creation / editing
        with st.expander("➕ " + ("إنشاء أو تعديل باقة تعاقدية مخصصة (Custom Plan Tier)" if is_ar else "Create or Edit Custom Contract Tier")):
            st.caption(
                "يمكنك إضافة سعة جديدة مخصصة بالكامل لعميل محدد (مثلاً باقة خاصة بـ 5000 رسالة و 50 ملف)."
                if is_ar
                else "Define custom quota limits tailored for a specific enterprise client."
            )

            col_p_id, col_p_name = st.columns([1, 1])
            with col_p_id:
                new_plan_id = st.text_input(
                    "معرّف الباقة بالإنجليزية (Plan ID)" if is_ar else "Plan Identifier (ID)",
                    placeholder="e.g. enterprise_500, vip_client, custom_tier",
                    key="new_plan_id_input",
                ).strip().lower()
            with col_p_name:
                new_plan_name = st.text_input(
                    "اسم الباقة (Plan Name)" if is_ar else "Plan Name",
                    placeholder="e.g. باقة المؤسسات الذهبية / Enterprise VIP",
                    key="new_plan_name_input",
                ).strip()

            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            with col_c1:
                p_ai = st.number_input(
                    "رسائل الذكاء/شهر" if is_ar else "Monthly AI Messages",
                    min_value=10,
                    max_value=100000,
                    value=500,
                    step=50,
                    key="new_p_ai",
                )
            with col_c2:
                p_ds = st.number_input(
                    "أقصى ملفات" if is_ar else "Max Datasets",
                    min_value=1,
                    max_value=500,
                    value=10,
                    step=1,
                    key="new_p_ds",
                )
            with col_c3:
                p_mb = st.number_input(
                    "أقصى حجم للملف (MB)" if is_ar else "Max File MB",
                    min_value=1,
                    max_value=200,
                    value=25,
                    step=5,
                    key="new_p_mb",
                )
            with col_c4:
                p_pdf = st.number_input(
                    "تقارير PDF/شهر" if is_ar else "PDF Exports/mo",
                    min_value=1,
                    max_value=1000,
                    value=50,
                    step=5,
                    key="new_p_pdf",
                )

            if st.button("💾 " + ("حفظ وتفعيل هذه الباقة في النظام" if is_ar else "Save Plan Definition"), key="btn_save_custom_plan"):
                if not new_plan_id or not new_plan_name:
                    st.error("يرجى إدخال معرّف واسم الباقة." if is_ar else "Please enter plan ID and name.")
                else:
                    plan_obj = PlanRecord(
                        id=new_plan_id,
                        name=new_plan_name,
                        monthly_ai_messages=int(p_ai),
                        max_datasets=int(p_ds),
                        max_file_mb=int(p_mb),
                        monthly_pdf_exports=int(p_pdf),
                        is_default=False,
                    )
                    self.auth_service.save_plan(plan_obj)
                    st.success(
                        f"✅ تم حفظ الباقة '{new_plan_name}' بنجاح! يمكنك الآن تعيينها لأي عميل."
                        if is_ar
                        else f"✅ Plan '{new_plan_name}' saved! You can now assign it to any client."
                    )
                    st.rerun()

    # -----------------------------------------------------------------------
    # Tab 3: Admin Security & Exclusivity
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
