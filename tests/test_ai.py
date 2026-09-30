from __future__ import annotations

"""Unit tests for AI Assistant module: LLMProvider, ToolExecutor, AIOrchestrator, and ChatView."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pydantic import SecretStr

from ai.orchestrator import AIOrchestrator
from ai.provider import LLMMessage, LLMProvider, LLMResponse
from ai.tools import ToolExecutor
from analytics.engine import DatasetContext
from core.config import Settings
from storage.base import DatasetRecord
from storage.local_backend import LocalBackend
from ui.session import SessionManager
from ui.views.chat_view import ChatView


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        llm_model="gemini/gemini-2.0-flash",
        llm_api_key=SecretStr("test-key-12345"),
        llm_fallback_model="gemini/gemini-1.5-flash",
        llm_fallback_api_key=SecretStr("fallback-key-12345"),
        admin_emails="admin@example.com",
    )


@pytest.fixture
def sample_dataset_context() -> DatasetContext:
    df = pd.DataFrame({
        "تاريخ": pd.date_range("2024-01-01", periods=10, freq="D"),
        "الصنف": ["لابتوب", "هاتف", "شاشة", "لوحة مفاتيح", "طابعة"] * 2,
        "الفئة": ["إلكترونيات", "إلكترونيات", "ملحقات", "ملحقات", "أجهزة"] * 2,
        "الكمية": [2, 5, 3, 10, 1, 4, 3, 2, 8, 2],
        "سعر الوحدة": [1000.0, 500.0, 300.0, 50.0, 800.0] * 2,
        "الإيراد": [2000.0, 2500.0, 900.0, 500.0, 800.0, 4000.0, 1500.0, 600.0, 400.0, 1600.0],
    })
    mapping = {
        "date": "تاريخ",
        "product": "الصنف",
        "category": "الفئة",
        "quantity": "الكمية",
        "unit_price": "سعر الوحدة",
        "revenue": "الإيراد",
    }
    return DatasetContext(
        sheets={"المبيعات": df},
        mapping=mapping,
        quality_summary={},
        dayfirst=True,
    )


# ---------------------------------------------------------------------------
# 1. LLMProvider Tests
# ---------------------------------------------------------------------------

def test_llm_message_and_response_models():
    msg = LLMMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"

    resp = LLMResponse(content="Answer", model="gemini/gemini-2.0-flash")
    assert resp.content == "Answer"
    assert not resp.has_tool_calls

    resp_with_tools = LLMResponse(
        tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "get_schema", "arguments": "{}"}}]
    )
    assert resp_with_tools.has_tool_calls


def test_sanitize_input():
    # Null bytes and control characters
    malicious = "Hello\x00World\x1f!\nThis is a test.````"
    cleaned = LLMProvider.sanitize_input(malicious)
    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned
    assert "````" not in cleaned
    assert cleaned.startswith("HelloWorld!")

    assert LLMProvider.sanitize_input("") == ""


def test_build_system_prompt(test_settings):
    provider = LLMProvider(test_settings)
    prompt_ar = provider.build_system_prompt(["المبيعات"], {"date": "تاريخ"}, language="ar")
    assert "REMO_OX Analytics" in prompt_ar
    assert "المبيعات" in prompt_ar
    assert "لا تقم أبداً بحساب" in prompt_ar

    prompt_en = provider.build_system_prompt(["Sales"], {"date": "Date"}, language="en")
    assert "REMO_OX Analytics" in prompt_en
    assert "Sales" in prompt_en
    assert "NEVER calculate" in prompt_en


def test_call_missing_model():
    empty_settings = Settings(llm_model="", admin_emails="admin@example.com")
    provider = LLMProvider(empty_settings)
    res = provider.call(messages=[{"role": "user", "content": "hi"}])
    assert res.error is not None
    assert "LLM_MODEL is not configured" in res.error


def test_call_primary_success(test_settings):
    provider = LLMProvider(test_settings)
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from Gemini"
    mock_choice.message.tool_calls = None
    mock_raw = MagicMock()
    mock_raw.choices = [mock_choice]
    mock_raw.usage.prompt_tokens = 10
    mock_raw.usage.completion_tokens = 20

    with patch("litellm.completion", return_value=mock_raw) as mock_comp:
        res = provider.call(messages=[{"role": "user", "content": "What is total sales?"}])
        assert mock_comp.called
        assert res.content == "Response from Gemini"
        assert res.model == "gemini/gemini-2.0-flash"
        assert res.prompt_tokens == 10


def test_call_fallback_on_primary_failure(test_settings):
    provider = LLMProvider(test_settings)

    mock_choice = MagicMock()
    mock_choice.message.content = "Response from Fallback"
    mock_choice.message.tool_calls = None
    mock_fallback_raw = MagicMock()
    mock_fallback_raw.choices = [mock_choice]

    # Primary raises exception, fallback succeeds
    with patch(
        "litellm.completion",
        side_effect=[RuntimeError("Quota limit on primary"), mock_fallback_raw],
    ) as mock_comp:
        res = provider.call(messages=[{"role": "user", "content": "Hello"}])
        assert mock_comp.call_count == 2
        assert res.content == "Response from Fallback"
        assert res.model == "gemini/gemini-1.5-flash"


def test_gemini_3_temperature_handling():
    # Gemini 3 model should omit temperature to avoid LiteLLM warnings
    g3_settings = Settings(
        llm_model="gemini/gemini-3.7-flash",
        llm_api_key=SecretStr("test-key"),
        admin_emails="admin@example.com",
    )
    provider = LLMProvider(g3_settings)

    mock_choice = MagicMock()
    mock_choice.message.content = "Gemini 3 response"
    mock_choice.message.tool_calls = None
    mock_raw = MagicMock()
    mock_raw.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_raw) as mock_comp:
        provider.call(messages=[{"role": "user", "content": "Hello"}])
        call_kwargs = mock_comp.call_args.kwargs
        assert "temperature" not in call_kwargs

    # Non-Gemini 3 model should include configured temperature
    non_g3_settings = Settings(
        llm_model="openai/gpt-4o-mini",
        llm_api_key=SecretStr("test-key"),
        admin_emails="admin@example.com",
    )
    provider_non_g3 = LLMProvider(non_g3_settings)
    with patch("litellm.completion", return_value=mock_raw) as mock_comp:
        provider_non_g3.call(messages=[{"role": "user", "content": "Hello"}])
        call_kwargs = mock_comp.call_args.kwargs
        assert "temperature" in call_kwargs
        assert call_kwargs["temperature"] == non_g3_settings.llm_temperature


def test_gemini_3_automatic_fallback():
    # If primary is Gemini 3 and fallback is empty, it automatically falls back to gemini-2.5-flash
    g3_settings = Settings(
        llm_model="gemini/gemini-3.7-flash",
        llm_api_key=SecretStr("test-key"),
        llm_fallback_model="",
        admin_emails="admin@example.com",
    )
    provider = LLMProvider(g3_settings)

    mock_choice = MagicMock()
    mock_choice.message.content = "Auto fallback response"
    mock_choice.message.tool_calls = None
    mock_raw = MagicMock()
    mock_raw.choices = [mock_choice]

    with patch(
        "litellm.completion",
        side_effect=[RuntimeError("503 Service Unavailable"), mock_raw],
    ) as mock_comp:
        res = provider.call(messages=[{"role": "user", "content": "Hello"}])
        assert mock_comp.call_count == 2
        # Second call used auto fallback model gemini/gemini-2.5-flash
        assert res.model == "gemini/gemini-2.5-flash"
        assert res.content == "Auto fallback response"


# ---------------------------------------------------------------------------
# 2. ToolExecutor Tests
# ---------------------------------------------------------------------------

def test_tool_executor_get_schema(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    out, tool_res, _note = executor.execute_tool("get_schema", "{}")
    assert "sheets" in out
    assert out["sheets"][0]["sheet_name"] == "المبيعات"
    assert tool_res is None


def test_tool_executor_aggregate(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    args = {
        "sheet_name": "المبيعات",
        "metrics": [{"column": "الإيراد", "agg": "sum"}],
        "group_by": ["الصنف"],
    }
    out, tool_res, _note = executor.execute_tool("aggregate", args)
    assert tool_res is not None
    assert len(tool_res.data) > 0
    assert "الإيراد" in str(out)


def test_tool_executor_top_n(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    args = {
        "sheet_name": "المبيعات",
        "category_column": "الصنف",
        "metric": {"column": "الإيراد", "agg": "sum"},
        "n": 3,
        "descending": True,
    }
    _out, tool_res, _note = executor.execute_tool("top_n", args)
    assert tool_res is not None
    assert len(tool_res.data) <= 3


def test_tool_executor_describe_column(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    args = {"sheet_name": "المبيعات", "column": "الإيراد"}
    _out, tool_res, _note = executor.execute_tool("describe_column", args)
    assert tool_res is not None


def test_tool_executor_run_report(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    args = {"report_id": "sales_overview", "sheet_name": "المبيعات"}
    out, _tool_res, _note = executor.execute_tool("run_report", args)
    assert out["report_id"] == "sales_overview"
    assert "kpis" in out


def test_tool_executor_invalid_tool_or_json(sample_dataset_context):
    executor = ToolExecutor(sample_dataset_context)
    # Invalid JSON
    out_bad_json, _, _ = executor.execute_tool("aggregate", "{bad json")
    assert "error" in out_bad_json

    # Unknown tool
    out_unknown, _, _ = executor.execute_tool("unknown_tool", {})
    assert "error" in out_unknown


# ---------------------------------------------------------------------------
# 3. AIOrchestrator Tests
# ---------------------------------------------------------------------------

def test_orchestrator_quota_exhausted(tmp_path, test_settings, sample_dataset_context):
    backend = LocalBackend(data_dir=tmp_path)
    _, user, _ = backend.sign_up("user@example.com", "pass123")
    assert user is not None

    # Mock quota check returning allowed=False
    with patch.object(backend, "check_quota", return_value=(False, 50, 50)):
        orchestrator = AIOrchestrator(backend=backend, settings=test_settings)
        res = orchestrator.chat(
            user_id=user.id,
            conversation_id=None,
            user_prompt="What is sales?",
            ctx=sample_dataset_context,
            language="ar",
        )
        assert res.error == "quota_exhausted"
        assert "استنفدت حصتك" in res.text


def test_orchestrator_rate_limited(tmp_path, test_settings, sample_dataset_context):
    backend = LocalBackend(data_dir=tmp_path)
    _, user, _ = backend.sign_up("user@example.com", "pass123")
    assert user is not None

    mock_limiter = MagicMock()
    mock_limiter.check_and_consume.return_value = False

    orchestrator = AIOrchestrator(backend=backend, settings=test_settings, rate_limiter=mock_limiter)
    res = orchestrator.chat(
        user_id=user.id,
        conversation_id=None,
        user_prompt="What is sales?",
        ctx=sample_dataset_context,
        language="ar",
    )
    assert res.error == "rate_limited"
    assert "الانتظار قليلاً" in res.text


def test_orchestrator_successful_chat_with_tools(tmp_path, test_settings, sample_dataset_context):
    backend = LocalBackend(data_dir=tmp_path)
    _, user, _ = backend.sign_up("user@example.com", "pass123")
    assert user is not None

    ds = DatasetRecord(
        id="ds_test_1",
        user_id=user.id,
        original_name="sales.xlsx",
        display_name="Sales",
        storage_path=f"{user.id}/ds_test_1/sales.xlsx",
        file_size_bytes=1000,
        sheet_names=["المبيعات"],
        row_counts={"المبيعات": 10},
        mapping={},
        quality={},
    )
    backend.create_dataset_record(ds)
    sample_dataset_context.dataset_id = ds.id

    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.sanitize_input.side_effect = lambda x: x
    mock_provider.build_system_prompt.return_value = "System prompt"

    # 1st call: returns tool call to aggregate
    tool_resp = LLMResponse(
        content=None,
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "aggregate",
                "arguments": '{"sheet_name": "المبيعات", "metrics": [{"column": "الإيراد", "agg": "sum"}]}',
            },
        }],
    )
    # 2nd call: returns final answer
    final_resp = LLMResponse(
        content="إجمالي الإيرادات هو 14,800 جنيه مصري.",
        tool_calls=[],
    )

    mock_provider.call.side_effect = [tool_resp, final_resp]

    orchestrator = AIOrchestrator(backend=backend, settings=test_settings, provider=mock_provider)
    res = orchestrator.chat(
        user_id=user.id,
        conversation_id=None,
        user_prompt="ما إجمالي الإيرادات؟",
        ctx=sample_dataset_context,
        language="ar",
    )

    assert res.error is None
    assert "14,800" in res.text
    assert len(res.tool_calls) == 1
    assert len(res.tool_results) == 1

    # Verify message was saved to storage backend
    assert res.conversation_id != ""
    msgs = backend.get_messages(res.conversation_id)
    assert len(msgs) == 2  # user and assistant


# ---------------------------------------------------------------------------
# 4. ChatView Tests
# ---------------------------------------------------------------------------

def test_chat_view_metadata(test_settings):
    session = SessionManager()
    session.set_language("ar")

    mock_ds = MagicMock()
    mock_auth = MagicMock()
    mock_orch = MagicMock()

    view = ChatView(
        session=session,
        dataset_service=mock_ds,
        auth_service=mock_auth,
        orchestrator=mock_orch,
        settings=test_settings,
    )

    assert view.get_title() == "المساعد الذكي"
    assert view.get_icon() == "💬"
    assert not view._check_privacy_consent()

    session.set_ai_consent(True)
    assert view._check_privacy_consent()
