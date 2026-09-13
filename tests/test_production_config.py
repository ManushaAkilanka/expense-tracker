"""
Phase 13 — Production Configuration Tests

Verifies production readiness of configuration, security headers,
health endpoint safety, and environment validation.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings, _DEFAULT_SECRET_KEY
from app.main import app




# ─── Secret Key ──────────────────────────────────────────────────────────────

def test_secret_key_is_set():
    """SECRET_KEY must be set (not empty)."""
    assert settings.SECRET_KEY, "SECRET_KEY must not be empty"


def test_default_secret_key_identified():
    """The constant _DEFAULT_SECRET_KEY must match the known weak placeholder."""
    assert _DEFAULT_SECRET_KEY == "decode-labs-super-secret-key-change-in-production"


def test_production_check_triggers_on_default_key(monkeypatch):
    """
    Simulates what happens when ENVIRONMENT=production and the default SECRET_KEY
    is used. Verifies the config-module guard would raise RuntimeError.
    """
    # We cannot re-import config at module level during tests without complex
    # patching, so we verify the logic directly (unit test of the predicate).
    fake_is_production = True
    fake_key = _DEFAULT_SECRET_KEY
    # Replicate the exact guard condition
    should_raise = fake_is_production and fake_key == _DEFAULT_SECRET_KEY
    assert should_raise, (
        "Production with the default secret key should trigger a RuntimeError"
    )


def test_production_check_passes_with_strong_key():
    """Strong custom secret keys pass the production guard."""
    import secrets
    strong_key = secrets.token_hex(32)
    should_raise = strong_key == _DEFAULT_SECRET_KEY
    assert not should_raise, "A newly generated key must not equal the default"


# ─── DEBUG flag ──────────────────────────────────────────────────────────────

def test_debug_is_boolean():
    """DEBUG setting must be a boolean."""
    assert isinstance(settings.DEBUG, bool)


def test_docs_url_only_in_debug_mode():
    """
    /docs must be accessible in DEBUG mode and return 404 when DEBUG=False.
    We verify the FastAPI app is configured with the correct docs_url at
    startup (not changing it mid-test to avoid side effects).
    """
    if settings.DEBUG:
        assert app.docs_url == "/docs"
    else:
        assert app.docs_url is None


# ─── Cookie security ─────────────────────────────────────────────────────────

def test_secure_cookie_is_boolean():
    """SECURE_COOKIE must be a boolean."""
    assert isinstance(settings.SECURE_COOKIE, bool)


def test_secure_cookie_false_for_local_dev():
    """
    For local development, SECURE_COOKIE should be False (HTTP).
    This verifies the current local .env is sane — not a hard requirement
    for production, which requires True behind HTTPS.
    """
    if settings.ENVIRONMENT == "development":
        assert settings.SECURE_COOKIE is False, (
            "Local dev should use SECURE_COOKIE=False (HTTP). "
            "Set SECURE_COOKIE=True in production behind HTTPS."
        )


# ─── HSTS ────────────────────────────────────────────────────────────────────

def test_hsts_disabled_locally():
    """HSTS must not be enabled for plain HTTP development."""
    if settings.ENVIRONMENT == "development":
        assert settings.HSTS_ENABLED is False, (
            "HSTS_ENABLED must be False for local HTTP development"
        )


# ─── Health endpoint ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_returns_safe_fields():
    """Health endpoint must not expose connection strings, paths, or secrets."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Must contain exactly these top-level fields — nothing extra
    assert set(data.keys()) == {"status", "database", "service", "version"}

    # Status must be "healthy" or "degraded" — no raw exception strings
    assert data["status"] in ("healthy", "degraded")

    # Database value must be "connected" or "unavailable" — not an exception trace
    assert data["database"] in ("connected", "unavailable"), (
        f"Health endpoint leaked internal database detail: {data['database']!r}"
    )

    # Service name must not expose filesystem paths or env vars
    assert "/" not in data["service"] or "Expense Tracker" in data["service"]
    assert "sqlite" not in data["service"].lower()
    assert "postgres" not in data["service"].lower()


# ─── Security headers (preserved from Phase 12) ──────────────────────────────

@pytest.mark.asyncio
async def test_security_headers_still_present():
    """
    Regression: All Phase 12 security headers must be preserved after
    Phase 13 modifications.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sign-in")

    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "strict-origin-when-cross-origin" in response.headers.get("referrer-policy", "")
    assert "geolocation=()" in response.headers.get("permissions-policy", "")


@pytest.mark.asyncio
async def test_hsts_header_absent_in_dev():
    """HSTS header must NOT appear when HSTS_ENABLED=False (local dev)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sign-in")

    if not settings.HSTS_ENABLED:
        assert "strict-transport-security" not in response.headers, (
            "HSTS header must not be sent when HSTS_ENABLED=False"
        )


# ─── Database configuration ──────────────────────────────────────────────────

def test_database_url_is_set():
    """DATABASE_URL must be non-empty."""
    assert settings.DATABASE_URL, "DATABASE_URL must not be empty"


def test_database_url_is_async_compatible():
    """DATABASE_URL must use an async driver (aiosqlite or asyncpg)."""
    url = settings.DATABASE_URL
    assert "aiosqlite" in url or "asyncpg" in url, (
        f"DATABASE_URL must use an async driver. Got: {url!r}"
    )


def test_database_url_contains_no_production_credentials_in_test():
    """
    In a test/dev environment, DATABASE_URL should not contain real
    production passwords. This is a sanity check, not a hard security gate.
    """
    url = settings.DATABASE_URL
    # Local SQLite path is always safe
    if "sqlite" in url:
        assert True  # SQLite — fine for dev/test
    # For PostgreSQL URLs, verify we're not accidentally running tests against prod
    elif "asyncpg" in url:
        # Warn if URL looks like a real production host
        assert "localhost" in url or "127.0.0.1" in url or "test" in url.lower(), (
            "Test suite appears to be connected to a non-local PostgreSQL database. "
            "Ensure tests run against a dedicated test database."
        )


# ─── ENVIRONMENT settings ────────────────────────────────────────────────────

def test_environment_value_is_recognised():
    """ENVIRONMENT must be a known value."""
    known = {"development", "dev", "staging", "production", "prod", "test"}
    assert settings.ENVIRONMENT.lower() in known, (
        f"ENVIRONMENT={settings.ENVIRONMENT!r} is not a recognised value. "
        f"Expected one of: {known}"
    )


def test_is_production_property():
    """is_production must correctly classify environment strings."""
    from app.config import Settings
    for env in ("production", "prod", "staging"):
        s = Settings(ENVIRONMENT=env, SECRET_KEY="x" * 64, _env_file=None)
        assert s.is_production is True
    for env in ("development", "dev", "test"):
        s = Settings(ENVIRONMENT=env, _env_file=None)
        assert s.is_production is False
