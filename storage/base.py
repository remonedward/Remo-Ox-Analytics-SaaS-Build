from __future__ import annotations

"""Abstract storage and authentication backend interface for REMO_OX Analytics.

This module defines the typed Protocol/ABC that all storage implementations
must satisfy. It guarantees clean decoupling between the UI layer and the
underlying database engine (Supabase PostgreSQL in cloud production,
SQLite in local development).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class UserSession:
    """Authenticated user session state."""

    id: str
    email: str
    role: str = "user"  # "user" | "admin"
    plan_id: str = "trial"
    is_active: bool = True
    language: str = "ar"  # "ar" | "en"
    consent_ai_at: str | None = None
    created_at: str | None = None

    @property
    def is_admin(self) -> bool:
        """Return True if user has administrator role."""
        return self.role == "admin"


@dataclass
class DatasetRecord:
    """Metadata record for an uploaded dataset."""

    id: str
    user_id: str
    original_name: str
    display_name: str
    storage_path: str
    file_size_bytes: int
    sheet_names: list[str]
    row_counts: dict[str, int]
    mapping: dict[str, str]
    quality: dict[str, Any]
    dayfirst: bool = False
    created_at: str | None = None
    expires_at: str | None = None


@dataclass
class ConversationRecord:
    """Chat conversation record for a user's dataset."""

    id: str
    user_id: str
    dataset_id: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class MessageRecord:
    """Individual chat message within a conversation."""

    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    tool_trace: list[dict[str, Any]] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: str | None = None


@dataclass
class PlanRecord:
    """Subscription plan tier configuration."""

    id: str
    name: str
    monthly_ai_messages: int
    max_datasets: int
    max_file_mb: int
    monthly_pdf_exports: int
    is_default: bool = False


@dataclass
class DatabaseDump:
    """Exportable database backup package for administrator download."""

    filename: str
    content_type: str  # "application/x-sqlite3" or "application/json" or "application/sql"
    data: bytes
    size_bytes: int
    created_at: str


class StorageBackend(ABC):
    """Abstract base class defining the contract for all storage backends."""

    # -----------------------------------------------------------------------
    # Authentication & User Management
    # -----------------------------------------------------------------------

    @abstractmethod
    def sign_up(self, email: str, password: str, language: str = "ar") -> tuple[bool, UserSession | None, str]:
        """Register a new user account.

        Returns:
            (success, user_session, error_message)
        """

    @abstractmethod
    def sign_in(self, email: str, password: str) -> tuple[bool, UserSession | None, str]:
        """Authenticate user credentials.

        Returns:
            (success, user_session, error_message)
        """

    @abstractmethod
    def sign_out(self, session: UserSession) -> None:
        """Terminate the active user session."""

    @abstractmethod
    def get_profile(self, user_id: str) -> UserSession | None:
        """Retrieve user profile by ID."""

    @abstractmethod
    def update_profile(self, user_id: str, updates: dict[str, Any]) -> bool:
        """Update profile fields (e.g. language, consent_ai_at)."""

    @abstractmethod
    def delete_user_data(self, user_id: str) -> bool:
        """Completely purge all datasets, messages, and exports for a user."""

    @abstractmethod
    def change_password(self, user_id: str, new_password: str) -> tuple[bool, str]:
        """Update a user's password.

        Returns:
            (success, error_message)
        """

    # -----------------------------------------------------------------------
    # Dataset Operations
    # -----------------------------------------------------------------------

    @abstractmethod
    def save_dataset_file(self, user_id: str, dataset_id: str, filename: str, file_bytes: bytes) -> str:
        """Store raw Excel file bytes securely.

        Returns:
            Internal storage path string.
        """

    @abstractmethod
    def get_dataset_file(self, storage_path: str) -> bytes | None:
        """Retrieve raw Excel file bytes by storage path."""

    @abstractmethod
    def create_dataset_record(self, record: DatasetRecord) -> bool:
        """Save dataset metadata to the database."""

    @abstractmethod
    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None:
        """Fetch dataset metadata with tenant ownership check."""

    @abstractmethod
    def list_datasets(self, user_id: str) -> list[DatasetRecord]:
        """List all datasets owned by a specific user."""

    @abstractmethod
    def update_dataset(self, dataset_id: str, user_id: str, updates: dict[str, Any]) -> bool:
        """Update dataset attributes (display_name, mapping, quality, dayfirst)."""

    @abstractmethod
    def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        """Delete dataset file and metadata."""

    # -----------------------------------------------------------------------
    # Conversations & Messages
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_or_create_conversation(self, user_id: str, dataset_id: str) -> ConversationRecord:
        """Retrieve the single conversation bound to (user_id, dataset_id) or create it."""

    @abstractmethod
    def get_messages(self, conversation_id: str, limit: int = 50) -> list[MessageRecord]:
        """Retrieve recent chat history ordered chronologically."""

    @abstractmethod
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_trace: list[dict[str, Any]] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> MessageRecord:
        """Append a new message to the conversation."""

    @abstractmethod
    def clear_conversation(self, conversation_id: str) -> bool:
        """Delete all messages in a conversation."""

    # -----------------------------------------------------------------------
    # Plans, Quotas & Usage Metering
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_plan(self, plan_id: str) -> PlanRecord | None:
        """Retrieve plan tier limits."""

    @abstractmethod
    def record_usage(
        self,
        user_id: str,
        kind: str,  # "ai_message" | "pdf_export" | "report_run"
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ) -> bool:
        """Log a billable usage event."""

    @abstractmethod
    def get_monthly_usage(self, user_id: str, kind: str) -> int:
        """Count usage events for the current calendar month."""

    @abstractmethod
    def check_quota(self, user_id: str, kind: str) -> tuple[bool, int, int]:
        """Check if user is within quota for kind.

        Returns:
            (allowed, used_this_month, limit_for_plan)
        """

    # -----------------------------------------------------------------------
    # Error Logging
    # -----------------------------------------------------------------------

    @abstractmethod
    def log_error(self, location: str, message: str, user_id: str | None = None) -> bool:
        """Log an unhandled error to the audit table."""

    # -----------------------------------------------------------------------
    # Administrator Tools & Full Database Backup
    # -----------------------------------------------------------------------

    @abstractmethod
    def list_all_users(self) -> list[UserSession]:
        """Admin-only: list all registered user profiles."""

    @abstractmethod
    def update_user_plan(self, user_id: str, new_plan_id: str) -> bool:
        """Admin-only: change a user's subscription tier."""

    @abstractmethod
    def list_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        """Admin-only: fetch recent system errors."""

    @abstractmethod
    def export_database_dump(self) -> DatabaseDump:
        """Admin-only: export a complete backup of the database for download.

        Returns:
            DatabaseDump containing bytes, filename, and mime type.
        """
