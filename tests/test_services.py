from __future__ import annotations

"""Unit tests for AuthService and DatasetService."""

from pathlib import Path

from core.config import Settings
from services.auth_service import AuthService
from services.dataset_service import DatasetService
from storage.local_backend import LocalBackend

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def test_auth_service_operations(temp_backend: LocalBackend, test_settings: Settings) -> None:
    """AuthService encapsulates validation, user management, and quota checks."""
    auth = AuthService(backend=temp_backend, settings=test_settings)

    # Empty credentials validation
    ok_empty, _, err_empty = auth.sign_up("", "")
    assert ok_empty is False
    assert "required" in err_empty

    # Short password validation
    ok_short, _, err_short = auth.sign_up("user@example.com", "123")
    assert ok_short is False
    assert "at least 6 characters" in err_short

    # Successful sign up
    ok, session, _ = auth.sign_up("user@example.com", "securepassword", language="ar")
    assert ok is True
    assert session is not None
    assert session.email == "user@example.com"

    # Sign in
    ok_in, user_in, _ = auth.sign_in("user@example.com", "securepassword")
    assert ok_in is True
    assert user_in.id == session.id

    # Update profile
    auth.update_profile(session.id, {"language": "en"})
    prof = auth.get_profile(session.id)
    assert prof is not None
    assert prof.language == "en"

    # Quota check & record usage
    allowed, used, limit = auth.check_quota(session.id, "ai_message")
    assert allowed is True
    assert used == 0
    assert limit == 20

    auth.record_usage(session.id, "ai_message", tokens_in=10, tokens_out=20)
    allowed2, used2, _ = auth.check_quota(session.id, "ai_message")
    assert allowed2 is True
    assert used2 == 1

    # Database dump
    dump = auth.export_database_dump()
    assert dump.size_bytes > 0


def test_dataset_service_lifecycle(temp_backend: LocalBackend, test_settings: Settings) -> None:
    """DatasetService handles validation, upload, mapping, and context loading."""
    auth = AuthService(backend=temp_backend, settings=test_settings)
    ds_service = DatasetService(backend=temp_backend, settings=test_settings)

    _, user, _ = auth.sign_up("analyst@example.com", "password123")
    assert user is not None

    sample_file = SAMPLE_DIR / "sales_en.xlsx"
    assert sample_file.exists()
    file_bytes = sample_file.read_bytes()

    # Upload and process
    ok, record, _err = ds_service.process_and_save_upload(
        user=user,
        filename="sales_en.xlsx",
        file_bytes=file_bytes,
        dayfirst=False,
    )
    assert ok is True
    assert record is not None
    assert record.id is not None
    assert "Sales" in record.sheet_names
    assert len(record.mapping) > 0

    # List datasets
    all_datasets = ds_service.list_datasets(user.id)
    assert len(all_datasets) == 1
    assert all_datasets[0].id == record.id

    # Load DatasetContext
    ctx = ds_service.load_dataset_context(record.id, user.id)
    assert ctx is not None
    assert "Sales" in ctx.sheets
    assert not ctx.sheets["Sales"].empty

    # Repeated load uses cache
    ctx_cached = ds_service.load_dataset_context(record.id, user.id)
    assert ctx_cached is ctx

    # Update mapping
    new_mapping = dict(record.mapping)
    new_mapping["product"] = "Product"
    ds_service.update_mapping(record.id, user.id, new_mapping)

    updated_record = ds_service.get_dataset(record.id, user.id)
    assert updated_record.mapping.get("product") == "Product"

    # Delete dataset
    deleted = ds_service.delete_dataset(record.id, user.id)
    assert deleted is True
    assert ds_service.get_dataset(record.id, user.id) is None
    assert len(ds_service.list_datasets(user.id)) == 0
