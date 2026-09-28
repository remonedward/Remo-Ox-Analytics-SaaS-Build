from __future__ import annotations

"""Unit tests for storage backends, multi-tenancy isolation, and database backup."""


from core.config import Settings
from storage import get_storage_backend
from storage.base import DatasetRecord
from storage.local_backend import LocalBackend


def test_auth_signup_and_signin(temp_backend: LocalBackend) -> None:
    """User can sign up and sign in with valid credentials."""
    # First user is automatically assigned admin role
    ok, session, err = temp_backend.sign_up("admin@example.com", "secret123", language="ar")
    assert ok is True
    assert session is not None
    assert session.role == "admin"
    assert session.email == "admin@example.com"
    assert not err

    # Second user is standard user
    ok2, session2, _ = temp_backend.sign_up("user@example.com", "password456", language="en")
    assert ok2 is True
    assert session2.role == "user"

    # Duplicate email rejected
    ok_dup, _, err_dup = temp_backend.sign_up("admin@example.com", "anotherpass")
    assert ok_dup is False
    assert "already exists" in err_dup

    # Valid sign in
    ok_in, user_in, _ = temp_backend.sign_in("admin@example.com", "secret123")
    assert ok_in is True
    assert user_in.id == session.id

    # Invalid password
    ok_bad, _, err_bad = temp_backend.sign_in("admin@example.com", "wrongpassword")
    assert ok_bad is False
    assert "Invalid email or password" in err_bad


def test_profile_update(temp_backend: LocalBackend) -> None:
    """Profile fields can be updated and retrieved."""
    _, session, _ = temp_backend.sign_up("u1@example.com", "pass12345")
    assert session is not None

    temp_backend.update_profile(session.id, {"language": "en", "consent_ai_at": "2026-01-01T00:00:00"})
    prof = temp_backend.get_profile(session.id)
    assert prof is not None
    assert prof.language == "en"
    assert prof.consent_ai_at == "2026-01-01T00:00:00"


def test_multi_tenant_dataset_isolation(temp_backend: LocalBackend) -> None:
    """User A cannot access or manipulate User B's datasets."""
    _, user_a, _ = temp_backend.sign_up("user_a@example.com", "pass_a_123")
    _, user_b, _ = temp_backend.sign_up("user_b@example.com", "pass_b_123")

    # User A creates dataset
    ds_a = DatasetRecord(
        id="ds_a_id",
        user_id=user_a.id,
        original_name="sales_a.xlsx",
        display_name="Sales A",
        storage_path=f"{user_a.id}/ds_a_id/sales_a.xlsx",
        file_size_bytes=1000,
        sheet_names=["Sales"],
        row_counts={"Sales": 10},
        mapping={},
        quality={},
    )
    temp_backend.create_dataset_record(ds_a)

    # User B creates dataset
    ds_b = DatasetRecord(
        id="ds_b_id",
        user_id=user_b.id,
        original_name="sales_b.xlsx",
        display_name="Sales B",
        storage_path=f"{user_b.id}/ds_b_id/sales_b.xlsx",
        file_size_bytes=2000,
        sheet_names=["Sales"],
        row_counts={"Sales": 20},
        mapping={},
        quality={},
    )
    temp_backend.create_dataset_record(ds_b)

    # User A can get their own dataset, but NOT User B's dataset
    assert temp_backend.get_dataset("ds_a_id", user_a.id) is not None
    assert temp_backend.get_dataset("ds_b_id", user_a.id) is None

    # User B can get their own dataset, but NOT User A's dataset
    assert temp_backend.get_dataset("ds_b_id", user_b.id) is not None
    assert temp_backend.get_dataset("ds_a_id", user_b.id) is None

    # List datasets is scoped strictly to user
    list_a = temp_backend.list_datasets(user_a.id)
    assert len(list_a) == 1
    assert list_a[0].id == "ds_a_id"

    # User A cannot delete User B's dataset
    del_forbidden = temp_backend.delete_dataset("ds_b_id", user_a.id)
    assert del_forbidden is False
    assert temp_backend.get_dataset("ds_b_id", user_b.id) is not None


def test_file_storage(temp_backend: LocalBackend) -> None:
    """Dataset files can be saved and retrieved accurately."""
    _, user, _ = temp_backend.sign_up("file_user@example.com", "pass12345")
    file_content = b"PK\x03\x04test_excel_binary_data"

    path = temp_backend.save_dataset_file(user.id, "ds_1", "test.xlsx", file_content)
    retrieved = temp_backend.get_dataset_file(path)
    assert retrieved == file_content


def test_conversations_and_messages(temp_backend: LocalBackend) -> None:
    """Conversations and messages are persisted chronologically."""
    _, user, _ = temp_backend.sign_up("chat_user@example.com", "pass12345")

    # Create dataset record to satisfy foreign key constraint
    ds = DatasetRecord(
        id="ds_100",
        user_id=user.id,
        original_name="test.xlsx",
        display_name="Test",
        storage_path=f"{user.id}/ds_100/test.xlsx",
        file_size_bytes=1000,
        sheet_names=["Sheet1"],
        row_counts={"Sheet1": 10},
        mapping={},
        quality={},
    )
    temp_backend.create_dataset_record(ds)

    conv = temp_backend.get_or_create_conversation(user.id, "ds_100")
    assert conv.id is not None

    # Re-calling returns the same conversation (unique constraint)
    conv_same = temp_backend.get_or_create_conversation(user.id, "ds_100")
    assert conv_same.id == conv.id

    # Add messages
    temp_backend.add_message(conv.id, "user", "What are the sales?", tokens_in=10)
    temp_backend.add_message(conv.id, "assistant", "Total is 50,000", tokens_out=25)

    history = temp_backend.get_messages(conv.id)
    assert len(history) == 2
    assert history[0].content == "What are the sales?"
    assert history[1].content == "Total is 50,000"

    # Clear conversation
    temp_backend.clear_conversation(conv.id)
    assert len(temp_backend.get_messages(conv.id)) == 0


def test_quotas_and_usage(temp_backend: LocalBackend) -> None:
    """Usage events are recorded and quota checks enforced."""
    _, user, _ = temp_backend.sign_up("quota_user@example.com", "pass12345")

    # Initial quota: trial has 20 monthly AI messages
    allowed, used, limit = temp_backend.check_quota(user.id, "ai_message")
    assert allowed is True
    assert used == 0
    assert limit == 20

    # Record 20 events
    for _ in range(20):
        temp_backend.record_usage(user.id, "ai_message", tokens_in=50, tokens_out=50)

    allowed_after, used_after, _ = temp_backend.check_quota(user.id, "ai_message")
    assert used_after == 20
    assert allowed_after is False  # Exceeded limit!


def test_admin_database_dump_export(temp_backend: LocalBackend) -> None:
    """Administrator can export a complete database dump for download."""
    temp_backend.sign_up("admin_backup@example.com", "admin_pass")

    dump = temp_backend.export_database_dump()
    assert dump is not None
    assert dump.filename.endswith(".sqlite")
    assert dump.content_type == "application/x-sqlite3"
    assert dump.size_bytes > 0
    assert len(dump.data) > 0


def test_get_storage_backend_factory(test_settings: Settings) -> None:
    """Factory returns LocalBackend when in local mode."""
    backend = get_storage_backend(test_settings, force_new=True)
    assert isinstance(backend, LocalBackend)
