"""
Centralized Application Configuration Management
All configuration values are populated strictly from environment variables.
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application & Runtime Environment
    PROJECT_NAME: str = "InternMatch AI"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Supabase Infrastructure Credentials (Server-side ONLY for service role)
    SUPABASE_URL: str = "https://placeholder-project.supabase.co"
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = "placeholder_jwt_secret_for_local_development"
    DATABASE_URL: str = (
        "postgresql://postgres:placeholder_password@placeholder_project.supabase.co:5432/postgres"
    )
    CV_STORAGE_BUCKET: str = "cvs"
    AVATAR_STORAGE_BUCKET: str = "avatars"

    # Redis Async Task Queue
    REDIS_URL: str = "redis://redis:6379/0"

    # Pinned AI Engine & Vector Search Models
    GEMINI_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gemini-3.5-flash"
    LLM_FALLBACK_MODEL_NAMES: str = (
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash"
    )
    # Canonical vector-space provider.
    #
    # Every candidate and internship vector MUST use the same provider/model.
    # Cross-provider embedding fallback is intentionally forbidden because
    # equal dimensions do not imply a compatible semantic vector space.
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_NAME: str = "gemini-embedding-2"
    OPENAI_EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # Independent generation-provider fallback.
    # Optional: Gemini remains primary when this key is absent.
    OPENAI_API_KEY: str = ""
    OPENAI_FALLBACK_MODEL_NAME: str = "gpt-5.6-luna"

    # RapidFuzz Skill Matching Threshold (MVP Default: 85)
    SKILL_FUZZY_THRESHOLD: int = 85

    # RevenueCat Integration Credentials
    REVENUECAT_PROJECT_ID: str = ""
    REVENUECAT_SECRET_KEY: str = ""
    REVENUECAT_ENVIRONMENT: str = "sandbox"

    # RevenueCat webhook security.
    # AUTH_TOKEN is the server-only token configured in RevenueCat's
    # webhook Authorization header.
    # SIGNING_SECRET enables HMAC verification when signing is enabled.
    REVENUECAT_WEBHOOK_AUTH_TOKEN: str = ""
    REVENUECAT_WEBHOOK_SIGNING_SECRET: str = ""

    # Security & CORS Origins Configuration
    # Comma-separated Supabase auth user UUIDs allowed to access
    # privileged InternMatch administrative endpoints.
    # Empty by default: administrative access fails closed.
    ADMIN_USER_IDS: str = ""
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:19006"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins string into a list."""
        if not self.ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


def validate_production_config(cfg: Settings) -> None:
    """
    Validate required settings when running in production environment.
    No-op when ENVIRONMENT != 'production'.
    Raises RuntimeError identifying invalid field names without leaking secrets.
    """
    if (cfg.ENVIRONMENT or "").strip().lower() != "production":
        return

    errors: List[str] = []

    # SUPABASE_URL
    sb_url = (cfg.SUPABASE_URL or "").strip()
    if not sb_url or "placeholder" in sb_url.lower() or not sb_url.startswith("https://"):
        errors.append("SUPABASE_URL (must be non-placeholder HTTPS URL)")

    # SUPABASE_SERVICE_ROLE_KEY
    sb_key = (cfg.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not sb_key or "placeholder" in sb_key.lower():
        errors.append("SUPABASE_SERVICE_ROLE_KEY (must be non-placeholder)")

    # SUPABASE_PUBLISHABLE_KEY
    sb_pub = (cfg.SUPABASE_PUBLISHABLE_KEY or "").strip()
    if not sb_pub or "placeholder" in sb_pub.lower():
        errors.append("SUPABASE_PUBLISHABLE_KEY (must be non-placeholder)")

    # DATABASE_URL
    db_url = (cfg.DATABASE_URL or "").strip()
    if not db_url or "placeholder" in db_url.lower():
        errors.append("DATABASE_URL (must be non-placeholder)")

    # REDIS_URL
    redis_url = (cfg.REDIS_URL or "").strip()
    if not redis_url or "placeholder" in redis_url.lower():
        errors.append("REDIS_URL (must be non-placeholder)")

    # GEMINI_API_KEY
    gemini_key = (cfg.GEMINI_API_KEY or "").strip()
    if not gemini_key or "placeholder" in gemini_key.lower():
        errors.append("GEMINI_API_KEY (must be non-placeholder)")

    # Canonical embedding provider
    embedding_provider = (
        cfg.EMBEDDING_PROVIDER or ""
    ).strip().lower()

    if embedding_provider not in {"gemini", "openai"}:
        errors.append(
            "EMBEDDING_PROVIDER (must be 'gemini' or 'openai')"
        )

    if embedding_provider == "openai":
        openai_key = (
            cfg.OPENAI_API_KEY or ""
        ).strip()

        if (
            not openai_key
            or "placeholder" in openai_key.lower()
        ):
            errors.append(
                "OPENAI_API_KEY "
                "(required when EMBEDDING_PROVIDER=openai)"
            )

    # CV_STORAGE_BUCKET
    cv_bucket = (cfg.CV_STORAGE_BUCKET or "").strip()
    if not cv_bucket:
        errors.append("CV_STORAGE_BUCKET (must be non-empty)")

    # AVATAR_STORAGE_BUCKET
    avatar_bucket = (cfg.AVATAR_STORAGE_BUCKET or "").strip()
    if not avatar_bucket:
        errors.append("AVATAR_STORAGE_BUCKET (must be non-empty)")

    # ALLOWED_ORIGINS
    origins = cfg.cors_origins_list
    if not origins:
        errors.append("ALLOWED_ORIGINS (must specify at least one origin)")
    else:
        for orig in origins:
            orig_lower = orig.lower()
            if (
                "*" in orig
                or "localhost" in orig_lower
                or "127.0.0.1" in orig_lower
                or not orig.startswith("https://")
            ):
                errors.append(
                    "ALLOWED_ORIGINS (must use https:// and cannot contain "
                    "*, localhost, or 127.0.0.1)"
                )
                break

    if errors:
        raise RuntimeError(f"Production configuration validation failed for: {', '.join(errors)}")


settings = Settings()
