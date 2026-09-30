from __future__ import annotations

"""Storage factory and public backend interfaces for REMO_OX Analytics."""

from core.config import Settings, get_settings
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
from storage.local_backend import LocalBackend

logger = get_logger(__name__)


_CACHED_BACKEND: StorageBackend | None = None


def get_storage_backend(
    settings: Settings | None = None,
    *,
    force_new: bool = False,
) -> StorageBackend:
    """Return the configured StorageBackend instance.

    If SUPABASE_URL and SUPABASE_ANON_KEY are present, connects to Supabase PostgreSQL.
    Otherwise, automatically falls back to LocalBackend (SQLite + local directory).

    Args:
        settings: Optional Settings override (uses cached app settings by default).
        force_new: If True, do not use the cached instance.

    Returns:
        Configured StorageBackend.
    """
    global _CACHED_BACKEND

    if not force_new and _CACHED_BACKEND is not None:
        return _CACHED_BACKEND

    cfg = settings or get_settings()

    if cfg.is_local_mode:
        logger.info("Initializing LocalBackend (SQLite + local filesystem)...")
        backend: StorageBackend = LocalBackend()
    else:
        try:
            from storage.supabase_backend import SupabaseBackend

            logger.info("Connecting to Supabase cloud PostgreSQL...")
            backend = SupabaseBackend(cfg)
        except Exception as exc:
            logger.warning(
                "Failed to connect to Supabase: %s. Falling back to LocalBackend.",
                exc,
            )
            backend = LocalBackend()

    _CACHED_BACKEND = backend
    return backend


__all__ = [
    "ConversationRecord",
    "DatabaseDump",
    "DatasetRecord",
    "LocalBackend",
    "MessageRecord",
    "PlanRecord",
    "StorageBackend",
    "UserSession",
    "get_storage_backend",
]
