from __future__ import annotations

"""Application configuration loaded from Streamlit secrets or environment variables.

All LLM provider settings are admin-only and never exposed to end users.
Secrets are read via st.secrets (production) with env var fallback (local dev).

Priority order:
    1. Streamlit secrets (``st.secrets``) — used in production/Streamlit Cloud.
    2. Environment variables / ``.env`` file — used in local development.
    3. Field defaults declared on the :class:`Settings` model.
"""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings for REMO_OX Analytics.

    Priority: Streamlit secrets → environment variables → defaults.
    Secrets (API keys) are stored as :class:`~pydantic.SecretStr` and are
    never logged or rendered to the UI.

    Attributes:
        llm_model: LiteLLM model string, e.g. ``openai/gpt-4o-mini``.
        llm_api_key: LLM provider API key (secret).
        llm_api_base: Optional custom API base URL (e.g. Azure endpoint).
        llm_temperature: Sampling temperature for LLM calls (0.0 – 2.0).
        llm_max_tokens: Maximum tokens per LLM response.
        llm_fallback_model: Optional fallback LiteLLM model string.
        llm_fallback_api_key: API key for the fallback model (secret).
        admin_emails: Comma-separated admin email addresses.
        default_plan: Default subscription plan for new users.
        max_upload_mb: Maximum upload file size in megabytes.
        max_rows: Maximum allowed rows per dataset.
        max_columns: Maximum allowed columns per dataset.
        retention_days: Days before uploaded datasets are purged.
        send_sample_rows_to_llm: Whether raw sample rows may be sent to the LLM.
        supabase_url: Supabase project URL (empty = local dev mode).
        supabase_anon_key: Supabase anon/public key (secret).
        supabase_service_key: Supabase service-role key (secret).
        app_name: Display name for the application.
        brand_primary_color: Hex colour used for primary brand elements.
        default_language: UI language; must be ``"ar"`` or ``"en"``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM (admin-only) ------------------------------------------------
    llm_model: str = Field(
        default="gemini/gemini-3.8-flash",
        description="LiteLLM model string, e.g. 'gemini/gemini-3.8-flash' (recommended), 'gemini/gemini-3.7-flash', etc.",
    )
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="LLM provider API key — never logged or displayed.",
    )
    llm_api_base: str = Field(
        default="",
        description="Optional custom API base URL (leave empty for default endpoints).",
    )
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for LLM completions.",
    )
    llm_max_tokens: int = Field(
        default=1500,
        ge=100,
        le=32000,
        description="Maximum tokens per LLM response.",
    )
    llm_fallback_model: str = Field(
        default="",
        description="Optional fallback LiteLLM model string.",
    )
    llm_fallback_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key for the fallback model — never logged or displayed.",
    )

    # ---- Admin & Plans ---------------------------------------------------
    admin_emails: str = Field(
        default="",
        description="Comma-separated list of administrator email addresses.",
    )
    default_plan: str = Field(
        default="trial",
        description="Default subscription plan assigned to newly registered users.",
    )

    # ---- Upload limits ---------------------------------------------------
    max_upload_mb: int = Field(
        default=10,
        ge=1,
        le=200,
        description="Maximum allowed upload file size in megabytes.",
    )
    max_rows: int = Field(
        default=200_000,
        ge=100,
        description="Maximum number of rows permitted per dataset.",
    )
    max_columns: int = Field(
        default=200,
        ge=10,
        description="Maximum number of columns permitted per dataset.",
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        description="Number of days before uploaded datasets are automatically purged.",
    )

    # ---- Privacy ---------------------------------------------------------
    send_sample_rows_to_llm: bool = Field(
        default=False,
        description=(
            "When True, up to 5 sample rows from the dataset may be included in LLM "
            "prompts. Enable only after reviewing the privacy implications."
        ),
    )

    # ---- Supabase --------------------------------------------------------
    supabase_url: str = Field(
        default="",
        description="Supabase project URL. Leave empty to run in local dev mode.",
    )
    supabase_anon_key: SecretStr = Field(
        default=SecretStr(""),
        description="Supabase anon/public key — never logged or displayed.",
    )
    supabase_service_key: SecretStr = Field(
        default=SecretStr(""),
        description="Supabase service-role key — never logged or displayed.",
    )

    # ---- Branding --------------------------------------------------------
    app_name: str = Field(
        default="REMO_OX Analytics",
        description="Application display name used in the UI and reports.",
    )
    brand_primary_color: str = Field(
        default="#1B4F72",
        description="Primary brand colour as a CSS hex string.",
    )
    default_language: str = Field(
        default="ar",
        description="Default UI language. Accepted values: 'ar', 'en'.",
    )

    # ---- Validators ------------------------------------------------------

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Coerce unsupported language codes to the default (Arabic).

        Args:
            v: Raw language value from config.

        Returns:
            ``"ar"`` or ``"en"``.
        """
        if v not in ("ar", "en"):
            return "ar"
        return v

    @field_validator("brand_primary_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Ensure the brand colour is a valid CSS hex string.

        Args:
            v: Raw colour value.

        Returns:
            Validated colour string.

        Raises:
            ValueError: If the string is not a valid 3- or 6-digit hex colour.
        """
        import re

        if not re.fullmatch(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", v):
            raise ValueError(
                f"BRAND_PRIMARY_COLOR must be a CSS hex colour (e.g. '#1B4F72'), got: {v!r}"
            )
        return v.upper() if len(v) == 7 else v

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Sanitize Supabase URL: strip whitespace, quotes, trailing slash, or auto-extract from dashboard link."""
        import re

        if not v:
            return ""
        val = str(v).strip().strip("'\"").rstrip("/")
        # If user accidentally entered dashboard URL:
        # e.g. https://supabase.com/dashboard/project/rfaittlumqzyisonnecf
        match = re.search(r"supabase\.com/dashboard/project/([a-zA-Z0-9_-]+)", val)
        if match:
            project_ref = match.group(1)
            val = f"https://{project_ref}.supabase.co"

        # Remove any path suffix like /rest/v1 or /auth/v1
        for suffix in ("/rest/v1", "/auth/v1"):
            if val.endswith(suffix):
                val = val[:-len(suffix)].rstrip("/")

        if val and not val.startswith("http://") and not val.startswith("https://"):
            val = f"https://{val}"

        return val

    # ---- Computed properties ---------------------------------------------

    @property
    def is_local_mode(self) -> bool:
        """Return ``True`` when running without Supabase (local dev mode).

        Local mode uses SQLite and the local filesystem instead of Supabase.
        """
        return not bool(
            self.supabase_url and self.supabase_anon_key.get_secret_value()
        )

    @property
    def admin_emails_list(self) -> list[str]:
        """Return the parsed, normalised list of administrator email addresses.

        Returns:
            Lowercased, stripped email strings. Empty list if none configured.
        """
        return [
            e.strip().lower()
            for e in self.admin_emails.split(",")
            if e.strip()
        ]

    @property
    def max_upload_bytes(self) -> int:
        """Return the maximum upload size converted to bytes.

        Returns:
            Integer byte count.
        """
        return self.max_upload_mb * 1024 * 1024

    # ---- Startup validation ----------------------------------------------

    def validate_startup(self) -> list[str]:
        """Validate critical configuration fields at application startup.

        This method checks for missing or inconsistent settings and returns
        human-readable diagnostic messages. It does **not** raise exceptions
        so that the application can surface these messages in the UI.

        Returns:
            A list of warning/error strings. An empty list indicates that all
            required fields are present and consistent.

        Note:
            API key values are **never** included in returned strings.
        """
        errors: list[str] = []

        if not self.llm_model:
            errors.append(
                "LLM_MODEL is not configured. The AI assistant will be unavailable. "
                "Set LLM_MODEL in Streamlit secrets (or the .env file) to enable it."
            )

        if self.llm_model and not self.llm_api_key.get_secret_value():
            errors.append(
                "LLM_MODEL is set but LLM_API_KEY is missing. "
                "The AI assistant will fail at runtime. "
                "Set LLM_API_KEY in Streamlit secrets."
            )

        if self.llm_fallback_model and not self.llm_fallback_api_key.get_secret_value():
            # Only warn — the primary key might work for the fallback too
            errors.append(
                "LLM_FALLBACK_MODEL is set but LLM_FALLBACK_API_KEY is empty. "
                "The fallback will use the primary LLM_API_KEY; "
                "set LLM_FALLBACK_API_KEY if the fallback uses a different provider."
            )

        if not self.admin_emails_list:
            errors.append(
                "ADMIN_EMAILS is not configured. No user will have admin access. "
                "Set ADMIN_EMAILS to a comma-separated list of administrator emails."
            )

        if self.max_upload_mb > 200:
            errors.append(
                f"MAX_UPLOAD_MB={self.max_upload_mb} exceeds the hard limit of 200 MB. "
                "This value will be clamped at runtime."
            )

        if not self.is_local_mode and not self.supabase_service_key.get_secret_value():
            errors.append(
                "SUPABASE_URL and SUPABASE_ANON_KEY are set but SUPABASE_SERVICE_KEY "
                "is missing. Admin operations (user management, RLS bypass) will fail."
            )

        return errors


# ---------------------------------------------------------------------------
# Streamlit-secrets source helper
# ---------------------------------------------------------------------------

def _load_from_streamlit_secrets() -> dict[str, Any]:
    """Attempt to read settings from Streamlit secrets.

    This function is intentionally lenient: if Streamlit is not installed,
    not running, or secrets are not configured, it returns an empty dict so
    the caller falls back to environment variables.

    Returns:
        A mapping of ``{field_name: value}`` for fields found in
        ``st.secrets``. Field names are lowercased to match the
        :class:`Settings` model.
    """
    try:
        import streamlit as st

        result: dict[str, Any] = {}
        secrets = st.secrets
        field_names = Settings.model_fields.keys()
        for field_name in field_names:
            upper_key = field_name.upper()
            if upper_key in secrets:
                result[field_name] = secrets[upper_key]
        return result
    except Exception:
        # Streamlit not running, secrets file missing, or any other issue.
        return {}


# ---------------------------------------------------------------------------
# Cached accessor
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application :class:`Settings` instance.

    Reads configuration from Streamlit secrets first, then falls back to
    environment variables and the ``.env`` file. The result is cached for
    the lifetime of the interpreter process.

    In unit tests, call ``get_settings.cache_clear()`` before patching
    environment variables to force re-construction.

    Returns:
        Fully validated :class:`Settings` instance.

    Example::

        from core.config import get_settings

        settings = get_settings()
        print(settings.app_name)
        print(settings.llm_model)
    """
    st_values = _load_from_streamlit_secrets()
    return Settings(**st_values)


def validate_at_startup() -> list[str]:
    """Convenience wrapper that loads settings and runs startup validation.

    Intended to be called once from the Streamlit entry point so that
    configuration problems are surfaced immediately on the admin panel
    rather than discovered at runtime.

    Returns:
        List of diagnostic strings. Empty list means configuration is valid.
    """
    return get_settings().validate_startup()


def update_env_file(updates: dict[str, str], env_path: str = ".env") -> None:
    """Update or append key-value pairs in the .env file and refresh in-memory settings.

    Args:
        updates: Dictionary of environment variable names to their new string values.
        env_path: Path to the target .env file (defaults to '.env').
    """
    import os
    from pathlib import Path

    p = Path(env_path)
    existing_lines: list[str] = []
    if p.exists():
        existing_lines = p.read_text(encoding="utf-8").splitlines()
    elif Path(".env.example").exists():
        existing_lines = Path(".env.example").read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    for key, val in updates.items():
        os.environ[key] = str(val)

    get_settings.cache_clear()

