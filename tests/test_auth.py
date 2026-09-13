import re
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.services.auth_service import register_user, authenticate_user


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="_csrf_token"\s+value="([^"]+)"', html)
    return match.group(1) if match else ""


@pytest.mark.asyncio
async def test_argon2_password_hashing():
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


@pytest.mark.asyncio
async def test_user_registration(db_session: AsyncSession):
    email = "test_register@decodelabs.dev"
    password = "ComplexPassword99!"
    user, error = await register_user(db_session, email=email, password=password, full_name="Test Dev")
    assert error is None
    assert user is not None
    assert user.email == email
    assert user.full_name == "Test Dev"

    # Duplicate registration must fail
    dup_user, dup_err = await register_user(db_session, email=email, password=password, full_name="Another Dev")
    assert dup_user is None
    assert dup_err is not None
    assert "already exists" in dup_err


@pytest.mark.asyncio
async def test_user_authentication(db_session: AsyncSession):
    email = "auth_test@decodelabs.dev"
    password = "AuthPassword123!"
    await register_user(db_session, email=email, password=password, full_name="Auth User")

    # Correct credentials
    user, err = await authenticate_user(db_session, email=email, password=password)
    assert err is None
    assert user is not None
    assert user.email == email

    # Incorrect password
    bad_user, bad_err = await authenticate_user(db_session, email=email, password="BadPassword")
    assert bad_user is None
    assert bad_err == "Invalid email or password."


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_sign_up_page_loads(client: AsyncClient):
    response = await client.get("/sign-up")
    assert response.status_code == 200
    assert "Expense Tracker" in response.text
    assert "Create Account" in response.text
    assert "Continue with Google" in response.text
    assert "_csrf_token" in response.text


@pytest.mark.asyncio
async def test_sign_in_page_loads(client: AsyncClient):
    response = await client.get("/sign-in")
    assert response.status_code == 200
    assert "Expense Tracker" in response.text
    assert "Sign In" in response.text
    assert "Continue with Google" in response.text
    assert "_csrf_token" in response.text


@pytest.mark.asyncio
async def test_valid_sign_up_and_dashboard_redirect(client: AsyncClient):
    get_res = await client.get("/sign-up")
    csrf_token = _extract_csrf(get_res.text)
    assert csrf_token

    post_res = await client.post(
        "/sign-up",
        data={
            "full_name": "New Developer",
            "email": "newdev@decodelabs.dev",
            "password": "Password1234!",
            "confirm_password": "Password1234!",
            "_csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert post_res.status_code == 303
    assert post_res.headers["location"] == "/dashboard"

    # Following to dashboard works and shows user info
    dash_res = await client.get("/dashboard")
    assert dash_res.status_code == 200
    assert "New Developer" in dash_res.text


@pytest.mark.asyncio
async def test_duplicate_email_rejected_in_ui(client: AsyncClient):
    get_res = await client.get("/sign-up")
    csrf_token = _extract_csrf(get_res.text)

    # First registration
    await client.post(
        "/sign-up",
        data={
            "full_name": "Dev One",
            "email": "unique_dev@decodelabs.dev",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "_csrf_token": csrf_token,
        },
    )

    # Clear cookies to simulate a second guest session attempting to register with same email
    client.cookies.clear()

    # Second registration with same email
    get_res2 = await client.get("/sign-up")
    csrf2 = _extract_csrf(get_res2.text)
    dup_res = await client.post(
        "/sign-up",
        data={
            "full_name": "Dev Two",
            "email": "unique_dev@decodelabs.dev",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "_csrf_token": csrf2,
        },
    )
    assert dup_res.status_code == 400
    assert "already registered" in dup_res.text


@pytest.mark.asyncio
async def test_invalid_email_format_rejected(client: AsyncClient):
    get_res = await client.get("/sign-up")
    csrf = _extract_csrf(get_res.text)

    res = await client.post(
        "/sign-up",
        data={
            "full_name": "Dev Invalid",
            "email": "not-an-email",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "_csrf_token": csrf,
        },
    )
    assert res.status_code == 400
    assert "valid email address" in res.text


@pytest.mark.asyncio
async def test_password_mismatch_rejected(client: AsyncClient):
    get_res = await client.get("/sign-up")
    csrf = _extract_csrf(get_res.text)

    res = await client.post(
        "/sign-up",
        data={
            "full_name": "Dev Mismatch",
            "email": "mismatch@decodelabs.dev",
            "password": "Password123!",
            "confirm_password": "DifferentPassword123!",
            "_csrf_token": csrf,
        },
    )
    assert res.status_code == 400
    assert "Passwords do not match" in res.text


@pytest.mark.asyncio
async def test_valid_sign_in_succeeds(client: AsyncClient, db_session: AsyncSession):
    await register_user(db_session, email="signin_dev@decodelabs.dev", password="SecurePassword123!", full_name="Sign In Dev")

    get_res = await client.get("/sign-in")
    csrf = _extract_csrf(get_res.text)

    post_res = await client.post(
        "/sign-in",
        data={
            "email": "signin_dev@decodelabs.dev",
            "password": "SecurePassword123!",
            "_csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert post_res.status_code == 303
    assert post_res.headers["location"] == "/dashboard"

    dash_res = await client.get("/dashboard")
    assert dash_res.status_code == 200
    assert "Sign In Dev" in dash_res.text


@pytest.mark.asyncio
async def test_invalid_credentials_fail_safely(client: AsyncClient):
    get_res = await client.get("/sign-in")
    csrf = _extract_csrf(get_res.text)

    post_res = await client.post(
        "/sign-in",
        data={
            "email": "nonexistent@decodelabs.dev",
            "password": "WrongPassword999!",
            "_csrf_token": csrf,
        },
    )
    assert post_res.status_code == 400
    assert "Invalid email or password." in post_res.text


@pytest.mark.asyncio
async def test_protected_dashboard_requires_authentication(client: AsyncClient):
    res = await client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 303
    assert "/sign-in" in res.headers["location"]


@pytest.mark.asyncio
async def test_logout_clears_session(client: AsyncClient, db_session: AsyncSession):
    await register_user(db_session, email="logout_dev@decodelabs.dev", password="Password123!", full_name="Logout Dev")

    get_res = await client.get("/sign-in")
    csrf = _extract_csrf(get_res.text)

    # Login
    await client.post(
        "/sign-in",
        data={
            "email": "logout_dev@decodelabs.dev",
            "password": "Password123!",
            "_csrf_token": csrf,
        },
    )

    # Dashboard is accessible
    dash_res = await client.get("/dashboard")
    assert dash_res.status_code == 200
    dash_csrf = _extract_csrf(dash_res.text)

    # Logout
    logout_res = await client.post(
        "/logout",
        data={"_csrf_token": dash_csrf},
        follow_redirects=False,
    )
    assert logout_res.status_code == 303
    assert logout_res.headers["location"] == "/sign-in"

    # Dashboard is now protected again
    after_res = await client.get("/dashboard", follow_redirects=False)
    assert after_res.status_code == 303
    assert "/sign-in" in after_res.headers["location"]


@pytest.mark.asyncio
async def test_csrf_protection_rejects_missing_or_invalid_token(client: AsyncClient):
    # Without CSRF token
    res_no_csrf = await client.post(
        "/sign-in",
        data={"email": "any@decodelabs.dev", "password": "Password123!"},
    )
    assert res_no_csrf.status_code == 403
    assert "CSRF" in res_no_csrf.text or "CSRF" in res_no_csrf.json().get("detail", "")

    # With forged/invalid CSRF token
    res_bad_csrf = await client.post(
        "/sign-in",
        data={"email": "any@decodelabs.dev", "password": "Password123!", "_csrf_token": "invalid_forged_token"},
    )
    assert res_bad_csrf.status_code == 403


@pytest.mark.asyncio
async def test_google_oauth_graceful_fallback_when_unconfigured(client: AsyncClient):
    response = await client.get("/auth/google")
    assert response.status_code in (200, 303)
    assert response.status_code != 500
    if response.status_code == 200:
        assert "Google OAuth" in response.text

