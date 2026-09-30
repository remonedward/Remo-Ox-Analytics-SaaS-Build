from __future__ import annotations

"""Dataset management service.

Handles ingestion, validation, role mapping, data quality evaluation,
storage persistence, and DatasetContext construction for analytics.
"""

import uuid
from typing import Any

import pandas as pd

from analytics.engine import DatasetContext
from analytics.schemas import QualityReport
from core.config import Settings
from core.logging_setup import get_logger
from core.security import ValidationResult, sanitize_filename, validate_upload
from data.ingest import IngestResult, read_excel
from data.mapping import apply_mapping, auto_map_roles
from data.quality import generate_quality_report
from storage.base import DatasetRecord, StorageBackend, UserSession

logger = get_logger(__name__)


class DatasetService:
    """Service providing end-to-end dataset lifecycle operations."""

    def __init__(self, backend: StorageBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings
        # In-memory cache for loaded DatasetContext instances: (user_id, dataset_id) -> DatasetContext
        self._context_cache: dict[tuple[str, str], DatasetContext] = {}

    def validate_file(
        self,
        file_bytes: bytes,
        filename: str,
        user: UserSession,
    ) -> ValidationResult:
        """Validate uploaded file for size, format, zip-bomb, and row/column limits."""
        plan = self._backend.get_plan(user.plan_id)
        return validate_upload(
            file_bytes=file_bytes,
            filename=filename,
            user_plan=plan,
            settings=self._settings,
        )

    def process_and_save_upload(
        self,
        user: UserSession,
        filename: str,
        file_bytes: bytes,
        dayfirst: bool = False,
        business_type: str = "products",
    ) -> tuple[bool, DatasetRecord | None, str]:
        """Ingest, clean, map, evaluate quality, and store an uploaded dataset.

        Returns:
            (success, dataset_record, error_message)
        """
        # Quota check
        plan = self._backend.get_plan(user.plan_id)
        existing = self._backend.list_datasets(user.id)
        if plan and len(existing) >= plan.max_datasets:
            return (
                False,
                None,
                f"Dataset limit reached ({len(existing)}/{plan.max_datasets}). Please upgrade or delete an older dataset.",
            )

        # Security validation
        val_res = self.validate_file(file_bytes, filename, user)
        if not val_res.is_valid:
            return False, None, "; ".join(val_res.errors)

        clean_name = sanitize_filename(filename)
        dataset_id = str(uuid.uuid4())

        try:
            # Deterministic Ingestion
            ingest_res: IngestResult = read_excel(file_bytes, dayfirst=dayfirst)
            if not ingest_res.sheets:
                return False, None, "No readable data found in the uploaded Excel file."

            # Pick default active sheet (first sheet)
            primary_sheet = ingest_res.sheet_names[0]
            primary_df = ingest_res.sheets[primary_sheet]

            # Automatic Mapping
            map_res = auto_map_roles(list(primary_df.columns))
            role_map = map_res.mapping

            # Quality Report
            quality_rep: QualityReport = generate_quality_report(
                sheets=ingest_res.sheets,
                mapping=role_map,
            )

            # Persist raw file
            storage_path = self._backend.save_dataset_file(
                user_id=user.id,
                dataset_id=dataset_id,
                filename=clean_name,
                file_bytes=file_bytes,
            )

            row_counts = {name: len(df) for name, df in ingest_res.sheets.items()}

            record = DatasetRecord(
                id=dataset_id,
                user_id=user.id,
                original_name=clean_name,
                display_name=clean_name.replace(".xlsx", ""),
                storage_path=storage_path,
                file_size_bytes=len(file_bytes),
                sheet_names=ingest_res.sheet_names,
                row_counts=row_counts,
                mapping=role_map,
                quality=quality_rep.model_dump(mode="json"),
                dayfirst=dayfirst,
                business_type=business_type,
            )

            self._backend.create_dataset_record(record)

            # Build and cache DatasetContext
            context = self._create_context(
                sheets=ingest_res.sheets,
                mapping=role_map,
                quality_report=quality_rep,
                dayfirst=dayfirst,
                dataset_id=dataset_id,
                business_type=business_type,
            )
            self._context_cache[(user.id, dataset_id)] = context

            logger.info("Successfully ingested dataset %s for user %s", dataset_id, user.id)
            return True, record, ""

        except Exception as exc:
            logger.error("Failed to ingest dataset %s: %s", clean_name, exc, exc_info=True)
            return False, None, f"Failed to process file: {exc}"

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None:
        """Fetch dataset metadata record."""
        return self._backend.get_dataset(dataset_id, user_id)

    def list_datasets(self, user_id: str) -> list[DatasetRecord]:
        """List all datasets owned by user."""
        return self._backend.list_datasets(user_id)

    def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        """Delete dataset from storage and cache."""
        self._context_cache.pop((user_id, dataset_id), None)
        return self._backend.delete_dataset(dataset_id, user_id)

    def update_mapping(
        self,
        dataset_id: str,
        user_id: str,
        new_mapping: dict[str, str],
        business_type: str | None = None,
    ) -> bool:
        """Update confirmed column mapping and optional business_type for a dataset."""
        record = self.get_dataset(dataset_id, user_id)
        if not record:
            return False

        updates: dict[str, Any] = {"mapping": new_mapping}
        if business_type:
            updates["business_type"] = business_type

        ok = self._backend.update_dataset(dataset_id, user_id, updates)
        if ok:
            # Invalidate context cache so it reloads with new mapping
            self._context_cache.pop((user_id, dataset_id), None)
        return ok

    def load_dataset_context(self, dataset_id: str, user_id: str) -> DatasetContext | None:
        """Load or retrieve cached DatasetContext for analytics execution."""
        cache_key = (user_id, dataset_id)
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        record = self.get_dataset(dataset_id, user_id)
        if not record:
            return None

        file_bytes = self._backend.get_dataset_file(record.storage_path)
        if not file_bytes:
            return None

        try:
            ingest_res = read_excel(file_bytes, dayfirst=record.dayfirst)
            quality_report = (
                QualityReport.model_validate(record.quality)
                if record.quality
                else generate_quality_report(ingest_res.sheets, record.mapping)
            )

            biz_type = getattr(record, "business_type", "products") or "products"

            context = self._create_context(
                sheets=ingest_res.sheets,
                mapping=record.mapping,
                quality_report=quality_report,
                dayfirst=record.dayfirst,
                dataset_id=dataset_id,
                business_type=biz_type,
            )
            self._context_cache[cache_key] = context
            return context
        except Exception as exc:
            logger.error("Failed to construct DatasetContext for %s: %s", dataset_id, exc)
            return None

    def _create_context(
        self,
        sheets: dict[str, pd.DataFrame],
        mapping: dict[str, str],
        quality_report: QualityReport,
        dayfirst: bool,
        dataset_id: str | None = None,
        business_type: str = "products",
    ) -> DatasetContext:
        """Construct a DatasetContext instance with derived columns applied."""
        mapped_sheets = {name: apply_mapping(df, mapping) for name, df in sheets.items()}
        quality_summaries = {name: quality_report.to_summary(name) for name in sheets}

        return DatasetContext(
            sheets=mapped_sheets,
            mapping=mapping,
            quality_summary=quality_summaries,
            dayfirst=dayfirst,
            send_sample_rows=self._settings.send_sample_rows_to_llm,
            dataset_id=dataset_id,
            business_type=business_type,
        )
