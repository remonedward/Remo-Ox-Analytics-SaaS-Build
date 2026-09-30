from __future__ import annotations

"""Supabase-based cloud production storage backend for REMO_OX Analytics.

Leverages PostgreSQL, Row Level Security (RLS), and Supabase Storage:
- Multi-tenant tenant isolation via auth.uid().
- Real-time connection pooling and scalable Postgres queries.
- Private cloud storage buckets for datasets and exports.
- Admin role elevation using SUPABASE_SERVICE_KEY.
- Complete cloud database export dump for administrator backup.
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

from core.config import Settings
from core.logging_setup import get_logger
from storage.base import (
    ConversationRecord,
    DatabaseDump,
    DatasetRecord,
    MessageRecord,
    PlanRecord,
    StorageBackend,
    TokenMessageLog,
    UserSession,
    UserTokenUsage,
)

logger = get_logger(__name__)


class SupabaseBackend(StorageBackend):
    """Production cloud storage backend powered by Supabase."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        url = self._sanitize_supabase_url(settings.supabase_url)
        anon_key = settings.supabase_anon_key.get_secret_value().strip().strip("'\"")
        service_key = settings.supabase_service_key.get_secret_value().strip().strip("'\"")

        if not url or not anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be provided.")

        from supabase import create_client

        self.client: Client = create_client(url, anon_key)
        self.admin_client: Client | None = (
            create_client(url, service_key) if service_key else None
        )

    @staticmethod
    def _sanitize_supabase_url(raw_url: str) -> str:
        import re

        if not raw_url:
            return ""
        val = str(raw_url).strip().strip("'\"").rstrip("/")
        match = re.search(r"supabase\.com/dashboard/project/([a-zA-Z0-9_-]+)", val)
        if match:
            project_ref = match.group(1)
            val = f"https://{project_ref}.supabase.co"

        for suffix in ("/rest/v1", "/auth/v1"):
            if val.endswith(suffix):
                val = val[:-len(suffix)].rstrip("/")

        if val and not val.startswith("http://") and not val.startswith("https://"):
            val = f"https://{val}"

        return val

    def _get_active_client(self, require_admin: bool = False) -> Client:
        if require_admin and self.admin_client:
            return self.admin_client
        return self.client

    # -----------------------------------------------------------------------
    # Authentication & User Management
    # -----------------------------------------------------------------------

    def sign_up(self, email: str, password: str, language: str = "ar") -> tuple[bool, UserSession | None, str]:
        email_clean = email.strip().lower()
        try:
            res = self.client.auth.sign_up({"email": email_clean, "password": password})
            if not res.user:
                return False, None, "Registration failed. Please try again."

            user_id = str(res.user.id)
            # The database trigger handle_new_user() creates the profile.
            # We fetch or update the profile language preference.
            profile = self.get_profile(user_id)
            if profile and profile.language != language:
                self.update_profile(user_id, {"language": language})
                profile.language = language

            return True, profile or UserSession(id=user_id, email=email_clean, language=language), ""
        except Exception as exc:
            logger.warning("Supabase sign_up error: %s", exc)
            exc_str = str(exc)
            if "User already registered" in exc_str:
                err_msg = "هذا البريد الإلكتروني مسجل بالفعل. يرجى تسجيل الدخول." if self.settings.default_language == "ar" else "User already registered. Please sign in."
                return False, None, err_msg
            return False, None, exc_str

    def sign_in(self, email: str, password: str) -> tuple[bool, UserSession | None, str]:
        email_clean = email.strip().lower()
        try:
            res = self.client.auth.sign_in_with_password({"email": email_clean, "password": password})
            if not res.user:
                return False, None, "Invalid email or password."

            user_id = str(res.user.id)
            profile = self.get_profile(user_id)
            if not profile:
                return False, None, "Profile record not found."
            if not profile.is_active:
                return False, None, "Account is disabled. Please contact support."

            return True, profile, ""
        except Exception as exc:
            logger.warning("Supabase sign_in error: %s", exc)
            exc_str = str(exc)
            if "Email not confirmed" in exc_str:
                err_msg = "يرجى تأكيد بريدك الإلكتروني من الرسالة المرسلة إليك أولاً (أو تعطيل تأكيد البريد من لوحة Supabase)." if self.settings.default_language == "ar" else "Please confirm your email address before signing in."
                return False, None, err_msg
            if "Invalid login credentials" in exc_str:
                err_msg = "البريد الإلكتروني أو كلمة المرور غير صحيحة." if self.settings.default_language == "ar" else "Invalid email or password."
                return False, None, err_msg
            return False, None, exc_str

    def sign_out(self, session: UserSession) -> None:
        try:
            self.client.auth.sign_out()
        except Exception as exc:
            logger.warning("Supabase sign_out error: %s", exc)

    def get_profile(self, user_id: str) -> UserSession | None:
        try:
            client = self._get_active_client()
            res = client.table("profiles").select("*").eq("id", user_id).execute()
            if not res.data:
                return None
            row = res.data[0]
            return UserSession(
                id=str(row["id"]),
                email=row["email"],
                role=row.get("role", "user"),
                plan_id=row.get("plan_id", "trial"),
                is_active=bool(row.get("is_active", True)),
                language=row.get("language", "ar"),
                consent_ai_at=row.get("consent_ai_at"),
                created_at=row.get("created_at"),
            )
        except Exception as exc:
            logger.warning("get_profile failed for %s: %s", user_id, exc)
            return None

    def update_profile(self, user_id: str, updates: dict[str, Any]) -> bool:
        try:
            client = self._get_active_client()
            client.table("profiles").update(updates).eq("id", user_id).execute()
            return True
        except Exception as exc:
            logger.warning("update_profile failed: %s", exc)
            return False

    def delete_user_data(self, user_id: str) -> bool:
        """Purge all datasets and files for user."""
        try:
            client = self._get_active_client()
            # Fetch storage paths to clean bucket
            res = client.table("datasets").select("storage_path").eq("user_id", user_id).execute()
            if res.data:
                paths = [r["storage_path"] for r in res.data if r.get("storage_path")]
                if paths:
                    client.storage.from_("datasets").remove(paths)

            client.table("datasets").delete().eq("user_id", user_id).execute()
            client.table("usage_events").delete().eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.warning("delete_user_data failed for %s: %s", user_id, exc)
            return False

    def change_password(self, user_id: str, new_password: str) -> tuple[bool, str]:
        """Update a user's password in Supabase."""
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters."
        try:
            client = self._get_active_client(require_admin=True)
            client.auth.admin.update_user_by_id(user_id, {"password": new_password})
            return True, ""
        except Exception as exc:
            logger.warning("change_password failed for %s: %s", user_id, exc)
            return False, str(exc)

    # -----------------------------------------------------------------------
    # Dataset Operations
    # -----------------------------------------------------------------------

    def save_dataset_file(self, user_id: str, dataset_id: str, filename: str, file_bytes: bytes) -> str:
        storage_path = f"{user_id}/{dataset_id}/{filename}"
        client = self._get_active_client()
        client.storage.from_("datasets").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        )
        return storage_path

    def get_dataset_file(self, storage_path: str) -> bytes | None:
        try:
            client = self._get_active_client()
            res = client.storage.from_("datasets").download(storage_path)
            return bytes(res)
        except Exception as exc:
            logger.warning("get_dataset_file failed for %s: %s", storage_path, exc)
            return None

    def create_dataset_record(self, record: DatasetRecord) -> bool:
        client = self._get_active_client()
        payload = {
            "id": record.id,
            "user_id": record.user_id,
            "original_name": record.original_name,
            "display_name": record.display_name,
            "storage_path": record.storage_path,
            "file_size_bytes": record.file_size_bytes,
            "sheet_names": record.sheet_names,
            "row_counts": record.row_counts,
            "mapping": record.mapping,
            "quality": record.quality,
            "dayfirst": record.dayfirst,
            "business_type": getattr(record, "business_type", "products") or "products",
            "created_at": record.created_at or datetime.now(UTC).isoformat(),
        }
        client.table("datasets").insert(payload).execute()
        return True

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None:
        client = self._get_active_client()
        res = client.table("datasets").select("*").eq("id", dataset_id).eq("user_id", user_id).execute()
        if not res.data:
            return None
        row = res.data[0]
        return DatasetRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            original_name=row["original_name"],
            display_name=row["display_name"],
            storage_path=row["storage_path"],
            file_size_bytes=row.get("file_size_bytes", 0),
            sheet_names=row.get("sheet_names", []),
            row_counts=row.get("row_counts", {}),
            mapping=row.get("mapping", {}),
            quality=row.get("quality", {}),
            dayfirst=bool(row.get("dayfirst", False)),
            business_type=row.get("business_type", "products"),
            created_at=row.get("created_at"),
            expires_at=row.get("expires_at"),
        )

    def list_datasets(self, user_id: str) -> list[DatasetRecord]:
        client = self._get_active_client()
        res = client.table("datasets").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        results = []
        for row in res.data:
            results.append(
                DatasetRecord(
                    id=str(row["id"]),
                    user_id=str(row["user_id"]),
                    original_name=row["original_name"],
                    display_name=row["display_name"],
                    storage_path=row["storage_path"],
                    file_size_bytes=row.get("file_size_bytes", 0),
                    sheet_names=row.get("sheet_names", []),
                    row_counts=row.get("row_counts", {}),
                    mapping=row.get("mapping", {}),
                    quality=row.get("quality", {}),
                    dayfirst=bool(row.get("dayfirst", False)),
                    business_type=row.get("business_type", "products"),
                    created_at=row.get("created_at"),
                    expires_at=row.get("expires_at"),
                )
            )
        return results

    def update_dataset(self, dataset_id: str, user_id: str, updates: dict[str, Any]) -> bool:
        client = self._get_active_client()
        client.table("datasets").update(updates).eq("id", dataset_id).eq("user_id", user_id).execute()
        return True

    def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        client = self._get_active_client()
        ds = self.get_dataset(dataset_id, user_id)
        if not ds:
            return False
        if ds.storage_path:
            try:
                client.storage.from_("datasets").remove([ds.storage_path])
            except Exception as e:
                logger.warning("Bucket removal error: %s", e)

        client.table("datasets").delete().eq("id", dataset_id).eq("user_id", user_id).execute()
        return True

    # -----------------------------------------------------------------------
    # Conversations & Messages
    # -----------------------------------------------------------------------

    def get_or_create_conversation(self, user_id: str, dataset_id: str) -> ConversationRecord:
        client = self._get_active_client()
        res = client.table("conversations").select("*").eq("user_id", user_id).eq("dataset_id", dataset_id).execute()
        if res.data:
            row = res.data[0]
            return ConversationRecord(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                dataset_id=str(row["dataset_id"]),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )

        # Create new
        payload = {"user_id": user_id, "dataset_id": dataset_id}
        ins = client.table("conversations").insert(payload).execute()
        row = ins.data[0]
        return ConversationRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            dataset_id=str(row["dataset_id"]),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def get_messages(self, conversation_id: str, limit: int = 50) -> list[MessageRecord]:
        client = self._get_active_client()
        res = (
            client.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return [
            MessageRecord(
                id=str(r["id"]),
                conversation_id=str(r["conversation_id"]),
                role=r["role"],
                content=r["content"],
                tool_trace=r.get("tool_trace"),
                tokens_in=r.get("tokens_in", 0),
                tokens_out=r.get("tokens_out", 0),
                created_at=r.get("created_at"),
            )
            for r in res.data
        ]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_trace: list[dict[str, Any]] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> MessageRecord:
        client = self._get_active_client()
        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "tool_trace": tool_trace,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        res = client.table("messages").insert(payload).execute()
        row = res.data[0]
        return MessageRecord(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            role=row["role"],
            content=row["content"],
            tool_trace=row.get("tool_trace"),
            tokens_in=row.get("tokens_in", 0),
            tokens_out=row.get("tokens_out", 0),
            created_at=row.get("created_at"),
        )

    def clear_conversation(self, conversation_id: str) -> bool:
        client = self._get_active_client()
        client.table("messages").delete().eq("conversation_id", conversation_id).execute()
        return True

    # -----------------------------------------------------------------------
    # Plans, Quotas & Usage Metering
    # -----------------------------------------------------------------------

    def get_plan(self, plan_id: str) -> PlanRecord | None:
        client = self._get_active_client()
        res = client.table("plans").select("*").eq("id", plan_id).execute()
        if not res.data:
            return None
        r = res.data[0]
        return PlanRecord(
            id=r["id"],
            name=r["name"],
            monthly_ai_messages=r["monthly_ai_messages"],
            max_datasets=r["max_datasets"],
            max_file_mb=r["max_file_mb"],
            monthly_pdf_exports=r["monthly_pdf_exports"],
            is_default=bool(r.get("is_default", False)),
        )

    def list_plans(self) -> list[PlanRecord]:
        client = self._get_active_client()
        res = client.table("plans").select("*").execute()
        return [
            PlanRecord(
                id=r["id"],
                name=r["name"],
                monthly_ai_messages=r["monthly_ai_messages"],
                max_datasets=r["max_datasets"],
                max_file_mb=r["max_file_mb"],
                monthly_pdf_exports=r["monthly_pdf_exports"],
                is_default=bool(r.get("is_default", False)),
            )
            for r in (res.data or [])
        ]

    def save_plan(self, plan: PlanRecord) -> bool:
        client = self._get_active_client(require_admin=True)
        payload = {
            "id": plan.id,
            "name": plan.name,
            "monthly_ai_messages": plan.monthly_ai_messages,
            "max_datasets": plan.max_datasets,
            "max_file_mb": plan.max_file_mb,
            "monthly_pdf_exports": plan.monthly_pdf_exports,
            "is_default": plan.is_default,
        }
        res = client.table("plans").upsert(payload).execute()
        return bool(res.data)


    def record_usage(
        self,
        user_id: str,
        kind: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ) -> bool:
        client = self._get_active_client()
        payload = {
            "user_id": user_id,
            "kind": kind,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "model": model,
        }
        client.table("usage_events").insert(payload).execute()
        return True

    def get_monthly_usage(self, user_id: str, kind: str) -> int:
        client = self._get_active_client()
        # Filter by current month beginning
        start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0).isoformat()
        res = (
            client.table("usage_events")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("kind", kind)
            .gte("created_at", start_of_month)
            .execute()
        )
        return int(res.count or 0)

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
            client = self._get_active_client()
            res = client.table("datasets").select("id", count="exact").eq("user_id", user_id).execute()
            used = int(res.count or 0)
        else:
            limit = 999_999

        return used < limit, used, limit

    # -----------------------------------------------------------------------
    # Error Logging
    # -----------------------------------------------------------------------

    def log_error(self, location: str, message: str, user_id: str | None = None) -> bool:
        try:
            client = self._get_active_client()
            client.table("app_errors").insert({"location": location, "message": message, "user_id": user_id}).execute()
            return True
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Administrator Tools & Full Database Backup
    # -----------------------------------------------------------------------

    def list_all_users(self) -> list[UserSession]:
        client = self._get_active_client(require_admin=True)
        res = client.table("profiles").select("*").order("created_at", desc=True).execute()
        return [
            UserSession(
                id=str(r["id"]),
                email=r["email"],
                role=r.get("role", "user"),
                plan_id=r.get("plan_id", "trial"),
                is_active=bool(r.get("is_active", True)),
                language=r.get("language", "ar"),
                consent_ai_at=r.get("consent_ai_at"),
                created_at=r.get("created_at"),
            )
            for r in res.data
        ]

    def update_user_plan(self, user_id: str, new_plan_id: str) -> bool:
        client = self._get_active_client(require_admin=True)
        client.table("profiles").update({"plan_id": new_plan_id}).eq("id", user_id).execute()
        return True

    def list_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        client = self._get_active_client(require_admin=True)
        res = client.table("app_errors").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data

    def export_database_dump(self) -> DatabaseDump:
        """Export all cloud tables into a consolidated JSON dump for admin download."""
        client = self._get_active_client(require_admin=True)
        tables = [
            "plans",
            "profiles",
            "datasets",
            "conversations",
            "messages",
            "usage_events",
            "exports",
            "app_errors",
        ]

        now = datetime.now(UTC)
        dump_data: dict[str, Any] = {
            "metadata": {
                "exported_at": now.isoformat(),
                "app_name": self.settings.app_name,
                "version": "1.0.0",
                "backend": "supabase_postgresql",
            },
            "tables": {},
        }

        for table in tables:
            try:
                res = client.table(table).select("*").execute()
                dump_data["tables"][table] = res.data
            except Exception as e:
                logger.warning("Could not dump table %s: %s", table, e)
                dump_data["tables"][table] = []

        raw_json = json.dumps(dump_data, indent=2, ensure_ascii=False).encode("utf-8")
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"remo_ox_cloud_dump_{timestamp}.json"

        return DatabaseDump(
            filename=filename,
            content_type="application/json",
            data=raw_json,
            size_bytes=len(raw_json),
            created_at=dump_data["metadata"]["exported_at"],
        )

    def get_users_token_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        user_id: str | None = None,
    ) -> list[UserTokenUsage]:
        """Admin-only: aggregate token consumption per user within a date range."""
        client = self._get_active_client(require_admin=True)

        profiles_query = client.table("profiles").select("id, email, plan_id")
        if user_id:
            profiles_query = profiles_query.eq("id", user_id)
        profiles_res = profiles_query.execute()
        profiles_data = profiles_res.data or []

        usage_query = client.table("usage_events").select("user_id, tokens_in, tokens_out, created_at").eq("kind", "ai_message")
        if start_date:
            sd = start_date if "T" in start_date else f"{start_date}T00:00:00"
            usage_query = usage_query.gte("created_at", sd)
        if end_date:
            ed = end_date if "T" in end_date else f"{end_date}T23:59:59"
            usage_query = usage_query.lte("created_at", ed)
        if user_id:
            usage_query = usage_query.eq("user_id", user_id)

        usage_res = usage_query.execute()
        usage_rows = usage_res.data or []

        user_stats: dict[str, dict[str, Any]] = {}
        for row in usage_rows:
            uid = str(row.get("user_id"))
            tin = int(row.get("tokens_in") or 0)
            tout = int(row.get("tokens_out") or 0)
            created = row.get("created_at")

            if uid not in user_stats:
                user_stats[uid] = {
                    "count": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "last_active": created,
                }
            user_stats[uid]["count"] += 1
            user_stats[uid]["tokens_in"] += tin
            user_stats[uid]["tokens_out"] += tout
            if created and (not user_stats[uid]["last_active"] or created > user_stats[uid]["last_active"]):
                user_stats[uid]["last_active"] = created

        summaries = []
        for p in profiles_data:
            pid = str(p["id"])
            st = user_stats.get(pid, {"count": 0, "tokens_in": 0, "tokens_out": 0, "last_active": None})
            summaries.append(
                UserTokenUsage(
                    user_id=pid,
                    email=p.get("email", ""),
                    plan_id=p.get("plan_id", "trial"),
                    total_messages=st["count"],
                    tokens_in=st["tokens_in"],
                    tokens_out=st["tokens_out"],
                    total_tokens=st["tokens_in"] + st["tokens_out"],
                    last_active=st["last_active"],
                )
            )

        summaries.sort(key=lambda x: (x.total_tokens, x.total_messages), reverse=True)
        return summaries

    def get_token_usage_events(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        user_id: str | None = None,
        limit: int = 200,
    ) -> list[TokenMessageLog]:
        """Admin-only: retrieve individual token usage events within a date range."""
        client = self._get_active_client(require_admin=True)

        q = client.table("usage_events").select("*").eq("kind", "ai_message")
        if start_date:
            sd = start_date if "T" in start_date else f"{start_date}T00:00:00"
            q = q.gte("created_at", sd)
        if end_date:
            ed = end_date if "T" in end_date else f"{end_date}T23:59:59"
            q = q.lte("created_at", ed)
        if user_id:
            q = q.eq("user_id", user_id)

        q = q.order("created_at", desc=True).limit(limit)
        events_res = q.execute()
        events_rows = events_res.data or []

        profiles_res = client.table("profiles").select("id, email").execute()
        email_map = {str(p["id"]): p.get("email", "") for p in (profiles_res.data or [])}

        logs = []
        for r in events_rows:
            uid = str(r.get("user_id"))
            tin = int(r.get("tokens_in") or 0)
            tout = int(r.get("tokens_out") or 0)
            logs.append(
                TokenMessageLog(
                    id=str(r.get("id")),
                    user_id=uid,
                    email=email_map.get(uid, ""),
                    kind=r.get("kind", "ai_message"),
                    tokens_in=tin,
                    tokens_out=tout,
                    total_tokens=tin + tout,
                    model=r.get("model"),
                    created_at=r.get("created_at", ""),
                )
            )
        return logs
