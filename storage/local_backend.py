from __future__ import annotations

"""SQLite-based local development storage backend for REMO_OX Analytics.

Provides full offline functionality when Supabase credentials are absent:
- SQLite embedded database with WAL mode and foreign key constraints.
- Local filesystem storage for uploaded datasets (.local_data/datasets/).
- Secure password hashing with PBKDF2-HMAC-SHA256.
- Multi-tenant data isolation.
- Full database backup / download capability for administrators.
"""

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_setup import get_logger
from storage.base import (
    ConversationRecord,
    DatabaseDump,
    DatasetRecord,
    MessageRecord,
    PlanRecord,
    StorageBackend,
    UserSession,
)

logger = get_logger(__name__)


def _hash_password(password: str, salt: bytes) -> str:
    """Hash password with PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()


class LocalBackend(StorageBackend):
    """Local SQLite and filesystem storage backend."""

    def __init__(self, data_dir: str | Path = ".local_data") -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "local_dev.db"
        self.datasets_dir = self.data_dir / "datasets"
        self.exports_dir = self.data_dir / "exports"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create and yield a SQLite connection, ensuring it is closed upon exit."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def close(self) -> None:
        """Close storage backend handles."""
        pass

    def _init_db(self) -> None:
        """Initialize database schema if not present."""
        with self._lock, self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    monthly_ai_messages INTEGER NOT NULL DEFAULT 20,
                    max_datasets INTEGER NOT NULL DEFAULT 1,
                    max_file_mb INTEGER NOT NULL DEFAULT 5,
                    monthly_pdf_exports INTEGER NOT NULL DEFAULT 3,
                    is_default BOOLEAN NOT NULL DEFAULT 0
                );

                INSERT OR IGNORE INTO plans (id, name, monthly_ai_messages, max_datasets, max_file_mb, monthly_pdf_exports, is_default)
                VALUES
                    ('trial', 'Trial', 20, 1, 5, 3, 1),
                    ('basic', 'Basic', 200, 5, 20, 20, 0),
                    ('pro', 'Pro', 1000, 20, 50, 100, 0);

                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    plan_id TEXT NOT NULL DEFAULT 'trial' REFERENCES plans(id),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    language TEXT NOT NULL DEFAULT 'ar',
                    consent_ai_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS local_credentials (
                    user_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    file_size_bytes INTEGER,
                    sheet_names TEXT NOT NULL DEFAULT '[]',
                    row_counts TEXT NOT NULL DEFAULT '{}',
                    mapping TEXT NOT NULL DEFAULT '{}',
                    quality TEXT NOT NULL DEFAULT '{}',
                    dayfirst BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    expires_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_datasets_user ON datasets(user_id);

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE (user_id, dataset_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_trace TEXT,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

                CREATE TABLE IF NOT EXISTS usage_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    model TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_events(user_id, kind);

                CREATE TABLE IF NOT EXISTS app_errors (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    location TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                UPDATE profiles SET plan_id = 'pro' WHERE role = 'admin' AND plan_id != 'pro';
                """
            )

    # -----------------------------------------------------------------------
    # Authentication & User Management
    # -----------------------------------------------------------------------

    def sign_up(self, email: str, password: str, language: str = "ar") -> tuple[bool, UserSession | None, str]:
        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean:
            return False, None, "Invalid email address format."
        if len(password) < 6:
            return False, None, "Password must be at least 6 characters."

        user_id = secrets.token_hex(16)
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(password, salt)

        with self._lock, self._get_connection() as conn:
            # Check existing email
            cur = conn.execute("SELECT id FROM profiles WHERE email = ?", (email_clean,))
            if cur.fetchone():
                return False, None, "An account with this email already exists."

            # Determine initial role from environment or profile count
            cur = conn.execute("SELECT count(*) as cnt FROM profiles")
            is_first = cur.fetchone()["cnt"] == 0

            admin_emails_env = [
                e.strip().lower()
                for e in os.environ.get("ADMIN_EMAILS", "").split(",")
                if e.strip()
            ]
            role = "admin" if email_clean in admin_emails_env or is_first else "user"

            plan_id = "pro" if email_clean in admin_emails_env else "trial"



            now_str = datetime.now(UTC).isoformat()
            conn.execute(
                """
                INSERT INTO profiles (id, email, role, plan_id, is_active, language, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (user_id, email_clean, role, plan_id, language, now_str, now_str),
            )
            conn.execute(
                "INSERT INTO local_credentials (user_id, password_hash, salt) VALUES (?, ?, ?)",
                (user_id, pw_hash, salt.hex()),
            )

        session = UserSession(
            id=user_id,
            email=email_clean,
            role=role,
            plan_id=plan_id,
            is_active=True,
            language=language,
            created_at=now_str,
        )
        return True, session, ""

    def sign_in(self, email: str, password: str) -> tuple[bool, UserSession | None, str]:
        email_clean = email.strip().lower()
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT p.id, p.email, p.role, p.plan_id, p.is_active, p.language, p.consent_ai_at, p.created_at,
                       c.password_hash, c.salt
                FROM profiles p
                JOIN local_credentials c ON p.id = c.user_id
                WHERE p.email = ?
                """,
                (email_clean,),
            )
            row = cur.fetchone()
            if not row:
                return False, None, "Invalid email or password."

            if not row["is_active"]:
                return False, None, "Account is disabled. Please contact support."

            salt = bytes.fromhex(row["salt"])
            computed_hash = _hash_password(password, salt)
            if not secrets.compare_digest(computed_hash, row["password_hash"]):
                return False, None, "Invalid email or password."

            session = UserSession(
                id=row["id"],
                email=row["email"],
                role=row["role"],
                plan_id=row["plan_id"],
                is_active=bool(row["is_active"]),
                language=row["language"],
                consent_ai_at=row["consent_ai_at"],
                created_at=row["created_at"],
            )
            return True, session, ""

    def sign_out(self, session: UserSession) -> None:
        """Local session termination is handled by Streamlit session_state."""
        pass

    def get_profile(self, user_id: str) -> UserSession | None:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM profiles WHERE id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return UserSession(
                id=row["id"],
                email=row["email"],
                role=row["role"],
                plan_id=row["plan_id"],
                is_active=bool(row["is_active"]),
                language=row["language"],
                consent_ai_at=row["consent_ai_at"],
                created_at=row["created_at"],
            )

    def update_profile(self, user_id: str, updates: dict[str, Any]) -> bool:
        if not updates:
            return True
        allowed_fields = {"language", "consent_ai_at", "role", "plan_id", "is_active"}
        set_clauses = []
        params = []
        for k, v in updates.items():
            if k in allowed_fields:
                set_clauses.append(f"{k} = ?")
                params.append(v)

        if not set_clauses:
            return True

        set_clauses.append("updated_at = datetime('now')")
        params.append(user_id)
        sql = f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ?"
        with self._lock, self._get_connection() as conn:
            conn.execute(sql, tuple(params))
        return True

    def delete_user_data(self, user_id: str) -> bool:
        """Purge user data and files completely."""
        with self._lock, self._get_connection() as conn:
            # Delete datasets records (cascade handles conversations and messages)
            conn.execute("DELETE FROM datasets WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM usage_events WHERE user_id = ?", (user_id,))

        user_dir = self.datasets_dir / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
        return True

    def change_password(self, user_id: str, new_password: str) -> tuple[bool, str]:
        """Update a user's password."""
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters."
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(new_password, salt)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE local_credentials SET password_hash = ?, salt = ? WHERE user_id = ?",
                (pw_hash, salt.hex(), user_id),
            )
        return True, ""

    # -----------------------------------------------------------------------
    # Dataset Operations
    # -----------------------------------------------------------------------

    def save_dataset_file(self, user_id: str, dataset_id: str, filename: str, file_bytes: bytes) -> str:
        dest_dir = self.datasets_dir / user_id / dataset_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        target_path = dest_dir / filename
        target_path.write_bytes(file_bytes)
        return f"{user_id}/{dataset_id}/{filename}"

    def get_dataset_file(self, storage_path: str) -> bytes | None:
        full_path = self.datasets_dir / storage_path
        if full_path.exists() and full_path.is_file():
            return full_path.read_bytes()
        return None

    def create_dataset_record(self, record: DatasetRecord) -> bool:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO datasets (
                    id, user_id, original_name, display_name, storage_path,
                    file_size_bytes, sheet_names, row_counts, mapping, quality,
                    dayfirst, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.original_name,
                    record.display_name,
                    record.storage_path,
                    record.file_size_bytes,
                    json.dumps(record.sheet_names),
                    json.dumps(record.row_counts),
                    json.dumps(record.mapping),
                    json.dumps(record.quality),
                    1 if record.dayfirst else 0,
                    record.created_at or datetime.now(UTC).isoformat(),
                    record.expires_at,
                ),
            )
        return True

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            return DatasetRecord(
                id=row["id"],
                user_id=row["user_id"],
                original_name=row["original_name"],
                display_name=row["display_name"],
                storage_path=row["storage_path"],
                file_size_bytes=row["file_size_bytes"] or 0,
                sheet_names=json.loads(row["sheet_names"]),
                row_counts=json.loads(row["row_counts"]),
                mapping=json.loads(row["mapping"]),
                quality=json.loads(row["quality"]),
                dayfirst=bool(row["dayfirst"]),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )

    def list_datasets(self, user_id: str) -> list[DatasetRecord]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM datasets WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            results = []
            for row in cur.fetchall():
                results.append(
                    DatasetRecord(
                        id=row["id"],
                        user_id=row["user_id"],
                        original_name=row["original_name"],
                        display_name=row["display_name"],
                        storage_path=row["storage_path"],
                        file_size_bytes=row["file_size_bytes"] or 0,
                        sheet_names=json.loads(row["sheet_names"]),
                        row_counts=json.loads(row["row_counts"]),
                        mapping=json.loads(row["mapping"]),
                        quality=json.loads(row["quality"]),
                        dayfirst=bool(row["dayfirst"]),
                        created_at=row["created_at"],
                        expires_at=row["expires_at"],
                    )
                )
            return results

    def update_dataset(self, dataset_id: str, user_id: str, updates: dict[str, Any]) -> bool:
        if not updates:
            return True
        allowed_fields = {"display_name", "mapping", "quality", "dayfirst"}
        clauses = []
        params = []
        for k, v in updates.items():
            if k in allowed_fields:
                clauses.append(f"{k} = ?")
                if isinstance(v, (dict, list)):
                    params.append(json.dumps(v))
                elif isinstance(v, bool):
                    params.append(1 if v else 0)
                else:
                    params.append(v)

        if not clauses:
            return True

        params.extend([dataset_id, user_id])
        sql = f"UPDATE datasets SET {', '.join(clauses)} WHERE id = ? AND user_id = ?"
        with self._lock, self._get_connection() as conn:
            conn.execute(sql, tuple(params))
        return True

    def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT storage_path FROM datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return False
            storage_path = row["storage_path"]
            conn.execute("DELETE FROM datasets WHERE id = ? AND user_id = ?", (dataset_id, user_id))

        # Delete local file and folder
        try:
            full_path = self.datasets_dir / storage_path
            if full_path.exists():
                full_path.unlink()
            parent = full_path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception as e:
            logger.warning("Could not delete dataset folder: %s", e)
        return True

    # -----------------------------------------------------------------------
    # Conversations & Messages
    # -----------------------------------------------------------------------

    def get_or_create_conversation(self, user_id: str, dataset_id: str) -> ConversationRecord:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM conversations WHERE user_id = ? AND dataset_id = ?",
                (user_id, dataset_id),
            )
            row = cur.fetchone()
            if row:
                return ConversationRecord(
                    id=row["id"],
                    user_id=row["user_id"],
                    dataset_id=row["dataset_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

            # Create new conversation
            conv_id = secrets.token_hex(16)
            now_str = datetime.now(UTC).isoformat()
            conn.execute(
                """
                INSERT INTO conversations (id, user_id, dataset_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conv_id, user_id, dataset_id, now_str, now_str),
            )
            return ConversationRecord(
                id=conv_id,
                user_id=user_id,
                dataset_id=dataset_id,
                created_at=now_str,
                updated_at=now_str,
            )

    def get_messages(self, conversation_id: str, limit: int = 50) -> list[MessageRecord]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            )
            msgs = []
            for row in cur.fetchall():
                msgs.append(
                    MessageRecord(
                        id=row["id"],
                        conversation_id=row["conversation_id"],
                        role=row["role"],
                        content=row["content"],
                        tool_trace=json.loads(row["tool_trace"]) if row["tool_trace"] else None,
                        tokens_in=row["tokens_in"] or 0,
                        tokens_out=row["tokens_out"] or 0,
                        created_at=row["created_at"],
                    )
                )
            return msgs

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_trace: list[dict[str, Any]] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> MessageRecord:
        msg_id = secrets.token_hex(16)
        now_str = datetime.now(UTC).isoformat()
        trace_json = json.dumps(tool_trace) if tool_trace else None

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, tool_trace, tokens_in, tokens_out, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, conversation_id, role, content, trace_json, tokens_in, tokens_out, now_str),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now_str, conversation_id),
            )

        return MessageRecord(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_trace=tool_trace,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            created_at=now_str,
        )

    def clear_conversation(self, conversation_id: str) -> bool:
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        return True

    # -----------------------------------------------------------------------
    # Plans, Quotas & Usage Metering
    # -----------------------------------------------------------------------

    def get_plan(self, plan_id: str) -> PlanRecord | None:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
            row = cur.fetchone()
            if not row:
                return None
            return PlanRecord(
                id=row["id"],
                name=row["name"],
                monthly_ai_messages=row["monthly_ai_messages"],
                max_datasets=row["max_datasets"],
                max_file_mb=row["max_file_mb"],
                monthly_pdf_exports=row["monthly_pdf_exports"],
                is_default=bool(row["is_default"]),
            )

    def record_usage(
        self,
        user_id: str,
        kind: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ) -> bool:
        event_id = secrets.token_hex(16)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (id, user_id, kind, tokens_in, tokens_out, cost_usd, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, user_id, kind, tokens_in, tokens_out, cost_usd, model),
            )
        return True

    def get_monthly_usage(self, user_id: str, kind: str) -> int:
        kinds = ("ai_message", "ai_messages") if kind in ("ai_message", "ai_messages") else (kind,)
        placeholders = ",".join("?" for _ in kinds)
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                f"""
                SELECT count(*) as cnt FROM usage_events
                WHERE user_id = ? AND kind IN ({placeholders})
                  AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
                """,
                (user_id, *kinds),
            )
            return int(cur.fetchone()["cnt"])

    def check_quota(self, user_id: str, kind: str) -> tuple[bool, int, int]:
        profile = self.get_profile(user_id)
        if not profile:
            return False, 0, 0

        plan = self.get_plan(profile.plan_id)
        if not plan:
            return False, 0, 0

        used = self.get_monthly_usage(user_id, kind)

        if kind in ("ai_message", "ai_messages"):
            limit = plan.monthly_ai_messages
            used = self.get_monthly_usage(user_id, "ai_message")
        elif kind == "pdf_export":
            limit = plan.monthly_pdf_exports
        elif kind == "dataset_upload":
            limit = plan.max_datasets
            # Count current active datasets
            with self._lock, self._get_connection() as conn:
                cur = conn.execute("SELECT count(*) as cnt FROM datasets WHERE user_id = ?", (user_id,))
                used = int(cur.fetchone()["cnt"])
        else:
            limit = 999_999

        allowed = used < limit
        return allowed, used, limit

    # -----------------------------------------------------------------------
    # Error Logging
    # -----------------------------------------------------------------------

    def log_error(self, location: str, message: str, user_id: str | None = None) -> bool:
        err_id = secrets.token_hex(16)
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO app_errors (id, user_id, location, message) VALUES (?, ?, ?, ?)",
                    (err_id, user_id, location, message),
                )
            return True
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Administrator Tools & Full Database Backup
    # -----------------------------------------------------------------------

    def list_all_users(self) -> list[UserSession]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM profiles ORDER BY created_at DESC")
            return [
                UserSession(
                    id=row["id"],
                    email=row["email"],
                    role=row["role"],
                    plan_id=row["plan_id"],
                    is_active=bool(row["is_active"]),
                    language=row["language"],
                    consent_ai_at=row["consent_ai_at"],
                    created_at=row["created_at"],
                )
                for row in cur.fetchall()
            ]

    def update_user_plan(self, user_id: str, new_plan_id: str) -> bool:
        plan = self.get_plan(new_plan_id)
        if not plan:
            return False
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE profiles SET plan_id = ?, updated_at = datetime('now') WHERE id = ?",
                (new_plan_id, user_id),
            )
        return True

    def list_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM app_errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def export_database_dump(self) -> DatabaseDump:
        """Create a complete SQLite database backup snapshot for download."""
        with self._lock, self._get_connection() as src_conn:
            # Checkpoint WAL so that all data is consolidated in the main db file
            src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

            raw_bytes = self.db_path.read_bytes() if self.db_path.exists() else b""
            now = datetime.now(UTC)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"remo_ox_backup_{timestamp}.sqlite"

            return DatabaseDump(
                filename=filename,
                content_type="application/x-sqlite3",
                data=raw_bytes,
                size_bytes=len(raw_bytes),
                created_at=now.isoformat(),
            )
