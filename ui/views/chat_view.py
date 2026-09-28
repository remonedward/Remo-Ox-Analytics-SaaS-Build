from __future__ import annotations

"""AI Assistant chat view with privacy consent, deterministic tool tracing, and interactive query suggestions."""

from typing import Any

from ai.orchestrator import AIOrchestrator
from analytics.charts import ChartRenderer
from core.config import Settings
from core.i18n import t
from core.logging_setup import get_logger
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from ui.session import SessionManager
from ui.views.base import BaseView

logger = get_logger(__name__)

SUGGESTED_PROMPTS_AR = [
    "ما إجمالي المبيعات وأفضل شهر؟",
    "من هم أفضل 5 عملاء أو منتجات مبيعاً؟",
    "هل يوجد أصناف راكدة في المخزون؟",
    "ما هو تفصيل وتوزيع المصروفات؟",
]

SUGGESTED_PROMPTS_EN = [
    "What is the total sales and peak month?",
    "Who are the top 5 customers or products?",
    "Are there any slow-moving items in stock?",
    "What is the breakdown of expenses by category?",
]


class ChatView(BaseView):
    """View managing the AI analytics conversation experience."""

    def __init__(
        self,
        session: SessionManager,
        dataset_service: DatasetService,
        auth_service: AuthService,
        orchestrator: AIOrchestrator,
        settings: Settings,
    ) -> None:
        super().__init__(session, dataset_service, auth_service, settings)
        self.orchestrator = orchestrator
        self.chart_renderer = ChartRenderer(
            primary_color=settings.brand_primary_color
        )

    def get_title(self) -> str:
        return t("ai_title", lang=self.language)

    def get_icon(self) -> str:
        return "💬"

    def render(self) -> None:
        """Render AI chat interface with consent gating and execution tracing."""
        try:
            import streamlit as st

            user = self.session.get_user()
            if not user:
                st.warning(t("account_inactive", lang=self.language))
                return

            # Privacy Consent Gate
            if not self._check_privacy_consent():
                self._render_privacy_consent_modal()
                return

            active_id = self.session.get_active_dataset_id()
            if not active_id:
                st.info(
                    "يرجى رفع ملف بيانات أو اختياره من القائمة الجانبية لبدء المحادثة مع المساعد الذكي."
                    if self.language == "ar"
                    else "Please upload or select a dataset from the sidebar to chat with the AI assistant."
                )
                return

            dataset = self.dataset_service.get_dataset(active_id, user.id)
            if not dataset:
                st.warning(t("no_datasets", lang=self.language))
                return

            ctx = self.dataset_service.load_dataset_context(dataset.id, user.id)
            if not ctx:
                st.error(t("error_generic", lang=self.language))
                return

            # Header & Quota Information
            col_head, col_act = st.columns([3, 1])
            with col_head:
                st.title(f"💬 {self.get_title()}")
                st.caption(f"الملف النشط: {dataset.display_name}")

            # Check monthly quota
            _, used, limit = self.orchestrator.check_user_quota(user.id)
            remaining = max(0, limit - used)

            # Get or create conversation bound to user and dataset
            conv = self.orchestrator.backend.get_or_create_conversation(user.id, dataset.id)
            conv_id = conv.id

            with col_act:
                st.metric(
                    label="رصيد الرسائل المتبقية" if self.language == "ar" else "Remaining Messages",
                    value=f"{remaining} / {limit}",
                )
                if st.button("➕ " + ("محادثة جديدة" if self.language == "ar" else "New Chat"), key="btn_new_chat", use_container_width=True):
                    self.orchestrator.backend.clear_conversation(conv_id)
                    st.rerun()

            st.divider()

            # Load message history
            history_messages: list[Any] = self.orchestrator.backend.get_messages(conv_id, limit=30)

            # Render message feed
            if history_messages:
                for msg in history_messages:
                    with st.chat_message(msg.role):
                        st.markdown(msg.content)
                        if getattr(msg, "tool_trace", None):
                            with st.expander("ℹ️ " + t("show_calculation", lang=self.language)):
                                for tc in msg.tool_trace:
                                    fn_name = tc.get("function", {}).get("name", "tool")
                                    args_str = tc.get("function", {}).get("arguments", "{}")
                                    st.code(f"Tool: {fn_name}\nArguments: {args_str}", language="json")
            else:
                st.info(
                    "مرحباً بك! أنا مساعدك التحليلي الذكي. يمكنك توجيه أي سؤال تحليلي حول أرقامك ومبيعاتك ومصروفاتك."
                    if self.language == "ar"
                    else "Welcome! I am your AI analytics assistant. Ask me any questions regarding your sales, inventory, or expenses."
                )
                # Show quick prompt suggestions
                st.subheader("💡 " + ("أسئلة مقترحة" if self.language == "ar" else "Suggested Questions"))
                prompts = SUGGESTED_PROMPTS_AR if self.language == "ar" else SUGGESTED_PROMPTS_EN
                p_cols = st.columns(len(prompts))
                for idx, prompt_text in enumerate(prompts):
                    with p_cols[idx]:
                        if st.button(prompt_text, key=f"sugg_prompt_{idx}", use_container_width=True):
                            self._submit_user_query(user.id, conv_id, prompt_text, ctx)
                            st.rerun()

            # Chat Input Box
            placeholder = t("ai_placeholder", lang=self.language)
            user_input = st.chat_input(placeholder=placeholder)
            if user_input:
                self._submit_user_query(user.id, conv_id, user_input, ctx)
                st.rerun()

        except Exception as exc:
            logger.error("Error in ChatView: %s", exc, exc_info=True)

    def _submit_user_query(self, user_id: str, conv_id: str | None, prompt: str, ctx: Any) -> None:
        """Handle execution and feedback for a user query."""
        import streamlit as st

        with st.spinner(t("ai_thinking", lang=self.language)):
            result = self.orchestrator.chat(
                user_id=user_id,
                conversation_id=conv_id,
                user_prompt=prompt,
                ctx=ctx,
                language=self.language,
            )

            # Store the resulting conversation ID in session
            if result.conversation_id:
                self.session.set("chat_conversation_id", result.conversation_id)

            if result.error:
                st.error(result.text)

    def _check_privacy_consent(self) -> bool:
        """Return True if user has accepted the privacy terms."""
        return self.session.has_ai_consent()

    def _render_privacy_consent_modal(self) -> None:
        """Render the explicit privacy notice required before AI usage."""
        import streamlit as st

        st.subheader("🛡️ " + t("ai_consent_title", lang=self.language))
        st.info(t("ai_consent_body", lang=self.language))

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button(
                "✅ " + t("ai_consent_accept", lang=self.language),
                type="primary",
                key="btn_consent_accept",
                use_container_width=True,
            ):
                self.session.set_ai_consent(True)
                st.rerun()

        with c2:
            if st.button(
                "❌ " + t("ai_consent_decline", lang=self.language),
                key="btn_consent_decline",
                use_container_width=True,
            ):
                st.warning(
                    "تم رفض المشاركة. يمكنك الاستمرار في استخدام التقارير الجاهزة والمخططات دون الحاجة للذكاء الاصطناعي."
                    if self.language == "ar"
                    else "Consent declined. You can continue using ready-made reports without AI."
                )
