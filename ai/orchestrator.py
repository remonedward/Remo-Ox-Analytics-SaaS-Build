from __future__ import annotations

"""Conversational AI orchestrator coordinating LLM turns, tool dispatching, and quota metering."""

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ai.provider import LLMProvider
from ai.tools import ANALYTICS_TOOLS, ToolExecutor
from analytics.engine import DatasetContext
from analytics.schemas import ToolResult
from core.config import Settings
from core.logging_setup import get_logger
from core.security import RateLimiter
from storage.base import StorageBackend

logger = get_logger(__name__)


class AIOrchestrationResult(BaseModel):
    """Encapsulates the response produced by an AI conversation turn."""

    text: str
    conversation_id: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    calculation_notes: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    remaining_quota: int = 0
    total_quota: int = 0
    error: str | None = None


class AIOrchestrator:
    """Coordinator handling conversational loops, rate limiting, and tool execution."""

    def __init__(
        self,
        backend: StorageBackend,
        settings: Settings,
        provider: LLMProvider | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.provider = provider or LLMProvider(settings)
        self.rate_limiter = rate_limiter or RateLimiter(max_tokens=20, window_seconds=60.0)

    def check_user_quota(self, user_id: str) -> tuple[bool, int, int]:
        """Check user's remaining AI message quota for the current month.

        Returns:
            (allowed, used, limit)
        """
        return self.backend.check_quota(user_id, "ai_message")

    def chat(
        self,
        user_id: str,
        conversation_id: str | None,
        user_prompt: str,
        ctx: DatasetContext,
        language: str = "ar",
    ) -> AIOrchestrationResult:
        """Run an end-to-end multi-turn conversation turn with deterministic tool calling."""
        # 1. Quota verification
        allowed, used, limit = self.check_user_quota(user_id)
        if not allowed:
            err_msg = (
                f"لقد استنفدت حصتك الشهرية من رسائل الذكاء الاصطناعي ({used}/{limit}). التقارير التفصيلية لا تزال متاحة بالكامل."
                if language == "ar"
                else f"You have exhausted your monthly AI message quota ({used}/{limit}). Detailed reports remain available."
            )
            return AIOrchestrationResult(
                text=err_msg,
                conversation_id=conversation_id or "",
                remaining_quota=0,
                total_quota=limit,
                error="quota_exhausted",
            )

        # 2. Rate limiter check
        if not self.rate_limiter.check_and_consume(user_id):
            wait_msg = (
                "يرجى الانتظار قليلاً قبل إرسال رسالة جديدة (تجاوز معدل الطلبات في الدقيقة)."
                if language == "ar"
                else "Please wait a moment before sending another message (rate limit exceeded)."
            )
            return AIOrchestrationResult(
                text=wait_msg,
                conversation_id=conversation_id or "",
                remaining_quota=max(0, limit - used),
                total_quota=limit,
                error="rate_limited",
            )

        # 3. Sanitize user prompt
        sanitized_prompt = self.provider.sanitize_input(user_prompt)
        if not sanitized_prompt:
            return AIOrchestrationResult(
                text="الرجاء كتابة سؤال محدد حول البيانات." if language == "ar" else "Please enter a specific question about your data.",
                conversation_id=conversation_id or "",
                remaining_quota=max(0, limit - used),
                total_quota=limit,
            )

        # 4. Conversation persistence initialization
        conv_id = conversation_id
        if not conv_id:
            dataset_id = getattr(ctx, "dataset_id", None) or "default_dataset"
            conv = self.backend.get_or_create_conversation(user_id=user_id, dataset_id=dataset_id)
            conv_id = conv.id

        # 5. Build conversation message history
        sheet_names = list(ctx.sheets.keys())
        biz_type = getattr(ctx, "business_type", "products")
        system_content = self.provider.build_system_prompt(
            sheet_names,
            ctx.mapping,
            language=language,
            business_type=biz_type,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
        ]

        # Load recent past turns (up to 10 previous messages for context window efficiency)
        past_msgs = self.backend.get_messages(conv_id, limit=10)
        for pm in past_msgs:
            messages.append({"role": pm.role, "content": pm.content})

        # Append current user prompt
        messages.append({"role": "user", "content": sanitized_prompt})

        # 6. Tool-calling execution loop (max 5 iterations)
        tool_executor = ToolExecutor(ctx)
        collected_tool_results: list[ToolResult] = []
        collected_calc_notes: list[str] = []
        collected_tool_calls: list[dict[str, Any]] = []

        total_prompt_tokens = 0
        total_completion_tokens = 0
        last_model = self.settings.llm_model

        final_text = ""
        max_tool_iterations = 5

        for _ in range(max_tool_iterations):
            resp = self.provider.call(messages=messages, tools=ANALYTICS_TOOLS)
            total_prompt_tokens += getattr(resp, "prompt_tokens", 0) or 0
            total_completion_tokens += getattr(resp, "completion_tokens", 0) or 0
            if resp.model:
                last_model = resp.model

            if resp.error:
                logger.warning("AI provider error during chat: %s", resp.error)
                fallback_msg = (
                    "خدمة المساعد الذكي غير متاحة حالياً بسبب خطأ في مزود الخدمة. يمكنك الاطلاع على تحليلاتك من خلال شاشة التقارير الجاهزة."
                    if language == "ar"
                    else "The AI service is temporarily unavailable. You can view your analytics via the Reports screen."
                )
                return AIOrchestrationResult(
                    text=fallback_msg,
                    conversation_id=conv_id,
                    remaining_quota=max(0, limit - used),
                    total_quota=limit,
                    error=resp.error,
                )

            if resp.has_tool_calls:
                # Append assistant tool-call turn
                messages.append({
                    "role": "assistant",
                    "content": resp.content or "",
                    "tool_calls": resp.tool_calls,
                })

                # Execute each tool deterministically
                for tc in resp.tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    call_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")

                    output_data, tool_res, calc_note = tool_executor.execute_tool(fn_name, fn_args)

                    if tool_res:
                        collected_tool_results.append(tool_res)
                    if calc_note:
                        collected_calc_notes.append(calc_note)
                    collected_tool_calls.append(tc)

                    # Append tool response
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": json.dumps(output_data, ensure_ascii=False),
                    })
            else:
                final_text = resp.content or ""
                break

        if not final_text and collected_tool_results:
            final_text = (
                "تم تنفيذ الحسابات والتحليلات المطلوبة بنجاح بناءً على بياناتك."
                if language == "ar"
                else "The requested calculations and analytics have been successfully computed from your data."
            )

        # 7. Record quota usage & token metering in database
        self.backend.record_usage(
            user_id=user_id,
            kind="ai_message",
            tokens_in=total_prompt_tokens,
            tokens_out=total_completion_tokens,
            model=last_model,
        )
        remaining = max(0, limit - (used + 1))

        # 8. Persist messages with tokens_in & tokens_out in database
        self.backend.add_message(conversation_id=conv_id, role="user", content=sanitized_prompt)
        self.backend.add_message(
            conversation_id=conv_id,
            role="assistant",
            content=final_text,
            tool_trace=collected_tool_calls if collected_tool_calls else None,
            tokens_in=total_prompt_tokens,
            tokens_out=total_completion_tokens,
        )

        return AIOrchestrationResult(
            text=final_text,
            conversation_id=conv_id,
            tool_calls=collected_tool_calls,
            calculation_notes=collected_calc_notes,
            tool_results=collected_tool_results,
            remaining_quota=remaining,
            total_quota=limit,
        )
