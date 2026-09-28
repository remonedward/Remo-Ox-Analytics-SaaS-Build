from __future__ import annotations

"""Unit tests for PDF export (export/pdf.py) and ExportService (services/export_service.py)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from analytics.charts import ChartRenderer
from analytics.schemas import KPICard, ReportResult, ToolResult
from core.config import get_settings
from export.pdf import PDFReportDocument, PDFReportGenerator
from services.export_service import ExportService


@pytest.fixture
def sample_report_result() -> ReportResult:
    return ReportResult(
        report_id="sales_overview",
        kpis=[
            KPICard(
                label="Total Revenue",
                value="250,000 EGP",
                delta="+12.5%",
                delta_positive=True,
            ),
            KPICard(
                label="Average Monthly",
                value="20,833 EGP",
            ),
        ],
        tables={
            "المبيعات الشهرية": ToolResult(
                data=[
                    {"Month": "2024-01", "Revenue": 15000.0, "Orders": 120},
                    {"Month": "2024-02", "Revenue": 18000.0, "Orders": 140},
                    {"Month": "2024-03", "Revenue": 22000.0, "Orders": 165},
                ],
                total_rows=3,
                truncated=False,
            )
        },
        calculation_description="تم تجميع إجمالي الإيرادات عبر دمج الكمية مع سعر الوحدة لكل شهر.",
    )


@pytest.fixture
def sample_chart_png() -> bytes:
    renderer = ChartRenderer()
    df = pd.DataFrame({"Category": ["A", "B", "C"], "Val": [10, 20, 30]})
    return renderer.render_png_bytes("hbar", df, "Category", "Val", title="Test")


def test_pdf_document_initialization():
    doc_ar = PDFReportDocument(app_name="REMO_OX Analytics", report_title="تقرير المبيعات", language="ar")
    assert doc_ar.language == "ar"
    assert doc_ar.app_name == "REMO_OX Analytics"
    assert doc_ar.active_font in ("Amiri", "Helvetica")

    doc_en = PDFReportDocument(app_name="REMO_OX Analytics", report_title="Sales Report", language="en")
    assert doc_en.language == "en"


def test_pdf_generator_arabic_with_chart(sample_report_result, sample_chart_png):
    generator = PDFReportGenerator(app_name="REMO_OX Analytics")
    pdf_bytes = generator.generate_report_pdf(
        report=sample_report_result,
        language="ar",
        chart_png_bytes=sample_chart_png,
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF starts with %PDF-
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_generator_english_without_chart(sample_report_result):
    generator = PDFReportGenerator(app_name="REMO_OX Analytics")
    pdf_bytes = generator.generate_report_pdf(
        report=sample_report_result,
        language="en",
        chart_png_bytes=None,
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")


def test_export_service_success(sample_report_result):
    mock_backend = MagicMock()
    mock_backend.check_quota.return_value = (True, 2, 10)

    settings = get_settings()
    service = ExportService(backend=mock_backend, settings=settings)

    success, pdf_bytes, err_msg = service.generate_report_pdf(
        user_id="test_user",
        report_result=sample_report_result,
        language="ar",
    )

    assert success is True
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF")
    assert err_msg == ""
    mock_backend.check_quota.assert_called_once_with("test_user", "pdf_export")
    mock_backend.record_usage.assert_called_once_with("test_user", "pdf_export")


def test_export_service_quota_exceeded(sample_report_result):
    mock_backend = MagicMock()
    mock_backend.check_quota.return_value = (False, 10, 10)

    settings = get_settings()
    service = ExportService(backend=mock_backend, settings=settings)

    # Test Arabic quota message
    success, pdf_bytes, err_msg = service.generate_report_pdf(
        user_id="test_user",
        report_result=sample_report_result,
        language="ar",
    )
    assert success is False
    assert pdf_bytes is None
    assert "استنفدت حصتك" in err_msg
    mock_backend.record_usage.assert_not_called()

    # Test English quota message
    success_en, _, err_msg_en = service.generate_report_pdf(
        user_id="test_user",
        report_result=sample_report_result,
        language="en",
    )
    assert success_en is False
    assert "Monthly PDF export limit reached" in err_msg_en


def test_export_service_exception_handling(sample_report_result):
    mock_backend = MagicMock()
    mock_backend.check_quota.return_value = (True, 1, 10)

    settings = get_settings()
    service = ExportService(backend=mock_backend, settings=settings)

    with patch.object(service._generator, "generate_report_pdf", side_effect=RuntimeError("Font rendering error")):
        success, pdf_bytes, err_msg = service.generate_report_pdf(
            user_id="test_user",
            report_result=sample_report_result,
            language="ar",
        )
        assert success is False
        assert pdf_bytes is None
        assert "فشل في إنشاء ملف PDF" in err_msg
