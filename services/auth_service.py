from __future__ import annotations

"""Authentication and User Management Service.

Encapsulates user session operations, credential validation, profile updates,
and quota tracking via the configured StorageBackend.
"""

from typing import Any

from core.config import Settings
from core.logging_setup import get_logger
from storage.base import DatabaseDump, PlanRecord, StorageBackend, UserSession

logger = get_logger(__name__)


class AuthService:
    """Service providing user authentication and profile management."""

    def __init__(self, backend: StorageBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings

    def sign_in(self, email: str, password: str) -> tuple[bool, UserSession | None, str]:
        """Authenticate user credentials."""
        if not email or not password:
            return False, None, "Email and password are required."
        ok, user, err = self._backend.sign_in(email.strip(), password)
        admin_emails = [e.lower() for e in self._settings.admin_emails_list]
        if ok and user and user.email.lower() in admin_emails and user.role != "admin":
            self._backend.update_profile(user.id, {"role": "admin"})
            user.role = "admin"
        return ok, user, err

    def sign_up(
        self,
        email: str,
        password: str,
        language: str = "ar",
    ) -> tuple[bool, UserSession | None, str]:
        """Register a new user account."""
        if not email or not password:
            return False, None, "Email and password are required."
        if len(password) < 6:
            return False, None, "Password must be at least 6 characters."
        ok, user, err = self._backend.sign_up(email.strip(), password, language=language)
        admin_emails = [e.lower() for e in self._settings.admin_emails_list]
        if ok and user and user.email.lower() in admin_emails and (user.role != "admin" or user.plan_id != "pro"):
            self._backend.update_profile(user.id, {"role": "admin", "plan_id": "pro"})
            user.role = "admin"
            user.plan_id = "pro"
        return ok, user, err

    def get_or_create_dev_admin(self, email: str = "admin@remox.com") -> UserSession:
        """Retrieve existing admin session or automatically create a developer admin session."""
        users = self._backend.list_all_users()
        admin_user = next((u for u in users if u.role == "admin" or u.email == email.lower()), None)
        if admin_user:
            return admin_user

        _ok, session, _err = self._backend.sign_up(email, "admin123456", language=self._settings.default_language)
        if session:
            self._backend.update_profile(session.id, {"role": "admin", "plan_id": "pro"})
            session.role = "admin"
            session.plan_id = "pro"
            return session
        return users[0] if users else UserSession(id="dev_admin", email=email, role="admin", plan_id="pro")

    def get_profile(self, user_id: str) -> UserSession | None:
        """Fetch current user session record."""
        return self._backend.get_profile(user_id)

    def update_profile(self, user_id: str, updates: dict[str, Any]) -> bool:
        """Update user profile fields."""
        return self._backend.update_profile(user_id, updates)

    def check_quota(self, user_id: str, kind: str) -> tuple[bool, int, int]:
        """Check if user has quota remaining for the specified event kind."""
        return self._backend.check_quota(user_id, kind)

    def record_usage(
        self,
        user_id: str,
        kind: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        model: str | None = None,
    ) -> bool:
        """Record a metered usage event."""
        return self._backend.record_usage(
            user_id=user_id,
            kind=kind,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
        )

    def export_database_dump(self) -> DatabaseDump:
        """Export full database backup for administrators."""
        return self._backend.export_database_dump()

    def get_plan(self, plan_id: str) -> PlanRecord | None:
        """Fetch plan details by plan_id."""
        return self._backend.get_plan(plan_id)

    def change_password(self, user_id: str, new_password: str) -> tuple[bool, str]:
        """Update user password."""
        return self._backend.change_password(user_id, new_password)

    def list_all_users(self) -> list[UserSession]:
        """Fetch all registered users (admin-only)."""
        return self._backend.list_all_users()

    def update_user_plan(self, user_id: str, new_plan_id: str) -> bool:
        """Assign or update a user's subscription plan tier (admin-only)."""
        return self._backend.update_user_plan(user_id, new_plan_id)

    def list_plans(self) -> list[PlanRecord]:
        """List all subscription plans and tiers."""
        return self._backend.list_plans()

    def save_plan(self, plan: PlanRecord) -> bool:
        """Create or update a subscription plan definition."""
        return self._backend.save_plan(plan)


