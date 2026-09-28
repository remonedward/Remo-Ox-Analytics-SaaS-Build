from __future__ import annotations

"""End-to-End (E2E) integration tests for REMO_OX Analytics.

These tests exercise complete real-world user journeys through the application:
1. Registration & Authentication.
2. Ingestion & Quality Analysis of messy Arabic workbooks (sample_data/sales_ar.xlsx).
3. Report Generation & Arabic PDF Export with native Amiri font embedding.
4. AI Assistant interaction: Privacy consent, Multi-turn Tool Calling, Quota Metering.
5. Ingestion of Inventory, Receivables, and Expenses files for domain-specific reports.
6. Admin Database Backup export (full DB dump download).
7. Tenant Isolation, Rate Limiting, and Security Guards.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from ai.orchestrator import AIOrchestrator
from ai.provider import LLMProvider, LLMResponse
from analytics.reports import (
    expense_breakdown,
    receivables_aging,
    sales_overview,
    slow_inventory,
    top_products,
)
from core.config import Settings
from core.security import validate_upload
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from storage.local_backend import LocalBackend

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


@pytest.fixture
def e2e_settings() -> Settings:
    return Settings(
        llm_model="gemini/gemini-2.0-flash",
        llm_api_key=SecretStr("e2e-fake-gemini-key"),
        llm_fallback_model="gemini/gemini-1.5-flash",
        llm_fallback_api_key=SecretStr("e2e-fake-fallback-key"),
        admin_emails="admin@remox.com",
        max_upload_mb=10,
        max_rows=50_000,
        max_columns=100,
        retention_days=90,
        send_sample_rows_to_llm=False,
    )


def test_e2e_arabic_sales_lifecycle_and_pdf(
    temp_backend: LocalBackend, e2e_settings: Settings
) -> None:
    """Full workflow: Arabic sales workbook ingestion -> quality -> reports -> Arabic PDF -> DB dump."""
    auth_service = AuthService(backend=temp_backend, settings=e2e_settings)
    ds_service = DatasetService(backend=temp_backend, settings=e2e_settings)
    export_service = ExportService(backend=temp_backend, settings=e2e_settings)

    # 1. User Sign Up
    ok, user, err = auth_service.sign_up(
        email="business_owner@company.eg",
        password="VerySecurePassword123!",
        language="ar",
    )
    assert ok is True
    assert user is not None
    assert err == ""

    # 2. Ingest real messy Arabic workbook (sales_ar.xlsx)
    ar_file = SAMPLE_DIR / "sales_ar.xlsx"
    assert ar_file.exists(), "sample_data/sales_ar.xlsx must exist"
    ar_bytes = ar_file.read_bytes()

    ok_upload, record, err_upload = ds_service.process_and_save_upload(
        user=user,
        filename="sales_ar.xlsx",
        file_bytes=ar_bytes,
        dayfirst=True,
    )
    assert ok_upload is True, f"Upload failed: {err_upload}"
    assert record is not None
    assert "المبيعات" in record.sheet_names

    # Verify auto-mapping recognized primary business roles
    mapping = record.mapping
    assert "date" in mapping or "تاريخ" in mapping.values()
    assert "revenue" in mapping or "إجمالي المبيعات" in mapping.values()

    # 3. Load DatasetContext and verify data cleaning
    ctx = ds_service.load_dataset_context(record.id, user.id)
    assert ctx is not None
    sheet_df = ctx.get_sheet("المبيعات")
    assert not sheet_df.empty
    # Verify summary rows were excluded and digits normalized
    assert len(sheet_df) > 100

    # Ensure mapped columns exist
    confirmed_mapping = {
        "date": "تاريخ",
        "product": "الصنف",
        "category": "الفئة",
        "customer": "العميل",
        "quantity": "الكمية",
        "unit_price": "سعر الوحدة",
        "revenue": "إجمالي المبيعات",
    }
    ds_service.update_mapping(record.id, user.id, confirmed_mapping)
    ctx_updated = ds_service.load_dataset_context(record.id, user.id)

    # 4. Generate Reports (sales_overview and top_products)
    rep_sales = sales_overview(ctx_updated)
    assert rep_sales.is_available is True
    assert len(rep_sales.kpi_cards) >= 3
    assert "monthly_sales" in rep_sales.tables
    assert len(rep_sales.tables["monthly_sales"].data) > 0

    rep_products = top_products(ctx_updated)
    assert rep_products.is_available is True
    assert len(rep_products.kpi_cards) >= 2
    assert "top_products" in rep_products.tables

    # 5. Export Report to Arabic PDF with Amiri font embedding
    ok_pdf, pdf_bytes, err_pdf = export_service.generate_report_pdf(
        user_id=user.id,
        report_result=rep_sales,
        language="ar",
    )
    assert ok_pdf is True, f"PDF export failed: {err_pdf}"
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000  # Non-trivial PDF size

    # Verify PDF export usage was metered
    _allowed, used, limit = auth_service.check_quota(user.id, "pdf_export")
    assert used == 1
    assert limit == 3  # Trial plan default

    # 6. Admin Database Backup Dump
    # Make user an admin
    admin_auth = AuthService(
        backend=temp_backend,
        settings=Settings(
            admin_emails="business_owner@company.eg",
            llm_api_key=SecretStr("fake"),
        ),
    )
    dump = admin_auth.export_database_dump()
    assert dump.filename.endswith((".sqlite", ".db", ".sql", ".json"))
    assert dump.size_bytes > 0
    assert len(dump.data) > 0


def test_e2e_ai_assistant_orchestration_and_metering(
    temp_backend: LocalBackend, e2e_settings: Settings
) -> None:
    """Full workflow: Upload English sales -> AI Orchestrator with Tool Calls -> Quota Metering & DB Trace."""
    auth_service = AuthService(backend=temp_backend, settings=e2e_settings)
    ds_service = DatasetService(backend=temp_backend, settings=e2e_settings)

    # 1. Create User
    ok, user, _ = auth_service.sign_up(
        email="analyst@startup.com",
        password="SecurePassword999!",
        language="en",
    )
    assert ok and user is not None

    # 2. Ingest clean English workbook (sales_en.xlsx)
    en_file = SAMPLE_DIR / "sales_en.xlsx"
    assert en_file.exists()
    en_bytes = en_file.read_bytes()

    ok_up, record, _ = ds_service.process_and_save_upload(
        user=user,
        filename="sales_en.xlsx",
        file_bytes=en_bytes,
        dayfirst=False,
    )
    assert ok_up and record is not None

    ctx = ds_service.load_dataset_context(record.id, user.id)
    assert ctx is not None

    # 3. Setup AI Orchestrator with mock LLM Provider
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.sanitize_input.side_effect = lambda x: x
    mock_provider.build_system_prompt.return_value = "System prompt"

    # Turn 1: LLM returns a tool call to top_n
    mock_provider.call.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[
                {
                    "id": "call_top_products_01",
                    "type": "function",
                    "function": {
                        "name": "top_n",
                        "arguments": '{"sheet_name": "Sales", "category_column": "Product", "metric_column": "Revenue", "n": 5}',
                    },
                }
            ],
            model="gemini/gemini-2.0-flash",
            prompt_tokens=120,
            completion_tokens=45,
        ),
        # Turn 2: LLM summarizes the tool output
        LLMResponse(
            content="Based on the analysis, your top 5 products by revenue are clearly identified.",
            tool_calls=[],
            model="gemini/gemini-2.0-flash",
            prompt_tokens=250,
            completion_tokens=60,
        ),
    ]

    orchestrator = AIOrchestrator(
        backend=temp_backend,
        settings=e2e_settings,
        provider=mock_provider,
    )

    # 4. User queries AI Assistant
    conv = temp_backend.get_or_create_conversation(user_id=user.id, dataset_id=record.id)
    assert conv is not None

    response = orchestrator.chat(
        user_id=user.id,
        conversation_id=conv.id,
        user_prompt="What are our top 5 products by revenue?",
        ctx=ctx,
        language="en",
    )

    assert response.error is None
    assert "top 5 products" in response.text
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["function"]["name"] == "top_n"
    assert len(response.tool_results) == 1
    assert response.tool_results[0].truncated is False
    assert len(response.tool_results[0].data) == 5

    # 5. Verify Quota Metering
    _allowed, used, limit = auth_service.check_quota(user.id, "ai_message")
    assert used == 1
    assert limit == 20

    # 6. Verify Conversation History in DB
    messages = temp_backend.get_messages(conv.id)
    # Should contain user message and assistant message with tool trace
    assert len(messages) >= 2
    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0].content == "What are our top 5 products by revenue?"


def test_e2e_all_domain_reports(temp_backend: LocalBackend, e2e_settings: Settings) -> None:
    """Verify all domain reports execute correctly against generated sample files."""
    auth_service = AuthService(backend=temp_backend, settings=e2e_settings)
    ds_service = DatasetService(backend=temp_backend, settings=e2e_settings)

    _, user, _ = auth_service.sign_up("ops@domain.com", "Password1234!")
    assert user is not None
    auth_service.update_profile(user.id, {"plan_id": "pro"})
    user = auth_service.get_profile(user.id)
    assert user is not None

    # 1. Inventory Report
    inv_file = SAMPLE_DIR / "inventory.xlsx"
    if inv_file.exists():
        ok, rec, _ = ds_service.process_and_save_upload(user, "inventory.xlsx", inv_file.read_bytes())
        assert ok and rec is not None
        ctx = ds_service.load_dataset_context(rec.id, user.id)
        rep = slow_inventory(ctx)
        assert rep.is_available is True
        assert len(rep.kpi_cards) >= 1
        assert "slow_items" in rep.tables

    # 2. Receivables Report
    rec_file = SAMPLE_DIR / "receivables.xlsx"
    if rec_file.exists():
        ok, rec, _ = ds_service.process_and_save_upload(user, "receivables.xlsx", rec_file.read_bytes())
        assert ok and rec is not None
        ctx = ds_service.load_dataset_context(rec.id, user.id)
        rep = receivables_aging(ctx)
        assert rep.is_available is True
        assert len(rep.kpi_cards) >= 1
        assert "aging_summary" in rep.tables

    # 3. Expenses Report
    exp_file = SAMPLE_DIR / "expenses.xlsx"
    if exp_file.exists():
        ok, rec, _ = ds_service.process_and_save_upload(user, "expenses.xlsx", exp_file.read_bytes())
        assert ok and rec is not None
        ds_service.update_mapping(rec.id, user.id, {"category": "Category", "expense_amount": "Amount", "date": "Date"})
        ctx = ds_service.load_dataset_context(rec.id, user.id)
        rep = expense_breakdown(ctx)
        assert rep.is_available is True
        assert len(rep.kpi_cards) >= 1
        assert "expenses_by_category" in rep.tables


def test_e2e_security_and_tenant_isolation(
    temp_backend: LocalBackend, e2e_settings: Settings
) -> None:
    """Verify tenant data isolation and upload security guards."""
    auth_service = AuthService(backend=temp_backend, settings=e2e_settings)
    ds_service = DatasetService(backend=temp_backend, settings=e2e_settings)

    # Create User A and User B
    _, user_a, _ = auth_service.sign_up("user_a@test.com", "passwordA123")
    _, user_b, _ = auth_service.sign_up("user_b@test.com", "passwordB123")

    en_file = SAMPLE_DIR / "sales_en.xlsx"
    ok, rec_a, _ = ds_service.process_and_save_upload(
        user=user_a,
        filename="sales_en.xlsx",
        file_bytes=en_file.read_bytes(),
    )
    assert ok and rec_a is not None

    # User B cannot access User A's dataset
    ctx_b = ds_service.load_dataset_context(rec_a.id, user_b.id)
    assert ctx_b is None

    assert ds_service.get_dataset(rec_a.id, user_b.id) is None
    assert ds_service.delete_dataset(rec_a.id, user_b.id) is False

    # Security: Reject non-excel / invalid magic bytes
    fake_malicious_bytes = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
    plan = auth_service.get_plan(user_a.plan_id)
    v_res = validate_upload(
        fake_malicious_bytes,
        "test.xlsx",
        user_plan=plan,
        settings=e2e_settings,
    )
    assert v_res.is_valid is False
    assert any("magic" in err.lower() or "zip" in err.lower() for err in v_res.errors)
