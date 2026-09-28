from __future__ import annotations

"""Export coordination service for generating branded reports and managing quotas."""

from analytics.schemas import ReportResult
from core.config import Settings
from core.logging_setup import get_logger
from export.pdf import PDFReportGenerator
from storage.base import StorageBackend

logger = get_logger(__name__)


class ExportService:
    """Service managing PDF generation and usage quotas."""

    def __init__(self, backend: StorageBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings
        self._generator = PDFReportGenerator(
            app_name=settings.app_name,
            brand_color_hex=settings.brand_primary_color,
        )

    def generate_report_pdf(
        self,
        user_id: str,
        report_result: ReportResult,
        language: str = "ar",
        chart_png_bytes: bytes | None = None,
    ) -> tuple[bool, bytes | None, str]:
        """Generate branded PDF report enforcing monthly export quota.

        Returns:
            (success, pdf_bytes, error_message)
        """
        # Quota verification
        allowed, used, limit = self._backend.check_quota(user_id, "pdf_export")
        if not allowed:
            msg = (
                f"لقد استنفدت حصتك الشهرية من تصدير التقارير ({used}/{limit}). يرجى ترقية باقتك."
                if language == "ar"
                else f"Monthly PDF export limit reached ({used}/{limit}). Please upgrade your plan."
            )
            return False, None, msg

        try:
            pdf_bytes = self._generator.generate_report_pdf(
                report=report_result,
                language=language,
                chart_png_bytes=chart_png_bytes,
            )

            # Record usage event
            self._backend.record_usage(user_id, "pdf_export")
            logger.info("Generated PDF report for user %s: %s bytes", user_id, len(pdf_bytes))
            return True, pdf_bytes, ""

        except Exception as exc:
            logger.error("Failed to generate PDF report: %s", exc, exc_info=True)
            err_msg = (
                f"فشل في إنشاء ملف PDF: {exc}"
                if language == "ar"
                else f"Failed to generate PDF: {exc}"
            )
            return False, None, err_msg
