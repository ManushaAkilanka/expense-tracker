import warnings
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET_KEY = "decode-labs-super-secret-key-change-in-production"


class Settings(BaseSettings):
    APP_NAME: str = "Expense Tracker"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"

    # Security
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    SESSION_COOKIE_NAME: str = "expense_session"
    SESSION_MAX_AGE: int = 86400  # 24 hours in seconds
    SECURE_COOKIE: bool = False

    # Production deployment options
    # Comma-separated list of allowed hosts (empty = allow all — development only)
    ALLOWED_HOSTS: str = ""
    # Set True when the app is behind an HTTPS-terminating reverse proxy
    # Enables Strict-Transport-Security header injection
    HSTS_ENABLED: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./expense_tracker.db"

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod", "staging")

    @property
    def is_google_oauth_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def allowed_hosts_list(self) -> List[str]:
        """Parse ALLOWED_HOSTS into a list. Empty list means unrestricted (dev only)."""
        if not self.ALLOWED_HOSTS:
            return []
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]


settings = Settings()

# ── Production safety checks ─────────────────────────────────────────────────
if settings.is_production and settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise RuntimeError(
        "FATAL: Production environment detected but SECRET_KEY is the insecure default. "
        "Set a strong SECRET_KEY environment variable before starting the server."
    )

if settings.DEBUG and settings.is_production:
    warnings.warn(
        "DEBUG=True in a production environment. Set DEBUG=False before deployment.",
        stacklevel=1,
    )

if settings.is_production and not settings.SECURE_COOKIE:
    warnings.warn(
        "SECURE_COOKIE=False in a production environment. "
        "Set SECURE_COOKIE=True when running behind HTTPS.",
        stacklevel=1,
    )
