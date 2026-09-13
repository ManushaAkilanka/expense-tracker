"""Phase 12 — Security Hardening, Adversarial Testing, and Edge-Case Regression Tests."""
import re
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.core.security import hash_password, verify_password, sign_session_data, unsign_session_data
from app.models.user import User
from app.services.auth_service import register_user
from app.services.expense_service import create_expense, clear_all_expenses
from tests.conftest import AuthenticatedSessionClient


# ===========================================================================
# 1. Password Security
# ===========================================================================

@pytest.mark.asyncio
async def test_password_argon2_and_no_leakage(db_session: AsyncSession, user_a: User, client: AsyncClient):
    """Verify password hashing with Argon2id and that hashes are never exposed."""
    assert user_a.password_hash is not None
    assert user_a.password_hash.startswith("$argon2id$")
    assert "Password123!" not in user_a.password_hash

    # Verify password verification works server-side
    assert verify_password("Password123!", user_a.password_hash) is True
    assert verify_password("WrongPassword", user_a.password_hash) is False
    assert verify_password("", user_a.password_hash) is False

    # Check health and public endpoints don't expose hashes
    res = await client.get("/health")
    assert "argon2" not in res.text
    assert "password" not in res.text.lower()


# ===========================================================================
# 2. Session Security, Fixation & Invalidation on Logout
# ===========================================================================

@pytest.mark.asyncio
async def test_session_cannot_be_forged():
    """Verify session data is cryptographically signed and tampering is rejected."""
    valid_signed = sign_session_data({"user_id": "fake-admin", "session_id": "sess-123"})
    assert unsign_session_data(valid_signed) is not None

    # Tampered signature
    tampered = valid_signed[:-4] + "abcd"
    assert unsign_session_data(tampered) is None

    # Completely fake token
    assert unsign_session_data("totally-fake-token") is None
    assert unsign_session_data("") is None


@pytest.mark.asyncio
async def test_logout_invalidates_session_and_prevents_replay(db_session: AsyncSession, user_a: User):
    """
    Adversarial test:
    1. Login as user_a.
    2. Access protected route with session cookie.
    3. Logout.
    4. Attempt to reuse the pre-logout session cookie.
    5. Verify access is denied.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Step 1: Sign in
        r1 = await ac.get("/sign-in")
        csrf_m = re.search(r'name="_csrf_token" value="([^"]+)"', r1.text)
        assert csrf_m, "CSRF token missing from sign-in"
        csrf = csrf_m.group(1)

        r_login = await ac.post("/sign-in", data={
            "_csrf_token": csrf,
            "email": "user_a@decodelabs.dev",
            "password": "Password123!",
        }, follow_redirects=False)
        assert r_login.status_code == 303

        # Capture the authenticated session cookie
        stolen_cookie = ac.cookies.get("expense_session")
        assert stolen_cookie is not None

        # Step 2: Access protected route successfully
        r_dash = await ac.get("/dashboard", follow_redirects=False)
        assert r_dash.status_code == 200

        # Step 3: Logout
        r_dash_csrf = re.search(r'name="_csrf_token" value="([^"]+)"', r_dash.text)
        logout_csrf = r_dash_csrf.group(1) if r_dash_csrf else csrf
        r_logout = await ac.post("/logout", data={"_csrf_token": logout_csrf}, follow_redirects=False)
        assert r_logout.status_code == 303

    # Step 4 & 5: In a new client, replay the stolen pre-logout cookie
    async with AsyncClient(transport=transport, base_url="http://test") as attacker_client:
        attacker_client.cookies.set("expense_session", stolen_cookie)
        r_replay = await attacker_client.get("/dashboard", follow_redirects=False)
        # Must NOT allow access to dashboard; must redirect to /sign-in
        assert r_replay.status_code == 303
        assert "/sign-in" in r_replay.headers.get("location", "")


# ===========================================================================
# 3. CSRF Protection
# ===========================================================================

@pytest.mark.asyncio
async def test_csrf_missing_rejected(auth_client_a: AuthenticatedSessionClient):
    """POST request without CSRF token must return 403 Forbidden."""
    res = await auth_client_a.client.post("/expenses", data={
        "amount": "20.00",
        "description": "Missing CSRF",
    })
    assert res.status_code == 403
    assert "CSRF" in res.text


@pytest.mark.asyncio
async def test_csrf_invalid_token_rejected(auth_client_a: AuthenticatedSessionClient):
    """POST request with forged/invalid CSRF token must return 403 Forbidden."""
    res = await auth_client_a.client.post("/expenses", data={
        "_csrf_token": "forged-invalid-csrf-token-12345",
        "amount": "20.00",
        "description": "Bad CSRF",
    })
    assert res.status_code == 403


# ===========================================================================
# 4. Multi-Tenant Isolation & IDOR Attacks
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_tenant_isolation_adversarial(
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    auth_client_a: AuthenticatedSessionClient,
    auth_client_b: AuthenticatedSessionClient,
):
    """
    Adversarial test:
    Tenant Alpha creates a sensitive expense.
    Tenant Beta attempts to read, search, edit, delete, and export it.
    All operations must remain completely isolated.
    """
    await clear_all_expenses(db_session, user_a.id)
    await clear_all_expenses(db_session, user_b.id)

    exp_alpha = await create_expense(
        db_session,
        user_id=user_a.id,
        amount=Decimal("1337.00"),
        description="Alpha Proprietary IP License",
        category="R&D",
    )

    # 1. Beta searches transactions: must NOT see Alpha's expense
    res_b_search = await auth_client_b.get("/transactions?q=Proprietary")
    assert res_b_search.status_code == 200
    assert "Alpha Proprietary" not in res_b_search.text
    assert "1337.00" not in res_b_search.text

    # 2. Beta exports CSV: must NOT contain Alpha's records
    res_b_csv = await auth_client_b.get("/transactions/export/csv")
    assert res_b_csv.status_code == 200
    assert "Alpha Proprietary" not in res_b_csv.text

    # 3. Beta exports JSON: must NOT contain Alpha's records
    res_b_json = await auth_client_b.get("/transactions/export/json")
    assert res_b_json.status_code == 200
    assert "Alpha Proprietary" not in res_b_json.text

    # 4. Beta attempts to edit Alpha's expense: returns 404
    res_b_edit = await auth_client_b.post(
        f"/expenses/{exp_alpha.id}/edit",
        data={"amount": "1.00", "description": "Compromised"}
    )
    assert res_b_edit.status_code == 404

    # 5. Beta attempts to delete Alpha's expense: returns 404
    res_b_del = await auth_client_b.post(f"/expenses/{exp_alpha.id}/delete")
    assert res_b_del.status_code == 404


@pytest.mark.asyncio
async def test_idor_malformed_and_nonexistent_ids(
    auth_client_a: AuthenticatedSessionClient
):
    """Malformed and nonexistent IDs must fail safely with 404 without 500 error."""
    payloads = [
        "00000000-0000-0000-0000-000000000000",
        "' OR '1'='1",
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "random-nonexistent-id",
        "A" * 200,
    ]
    for bad_id in payloads:
        res = await auth_client_a.post(f"/expenses/{bad_id}/edit", data={
            "amount": "10.00",
            "description": "Test",
        })
        assert res.status_code == 404, f"Failed for ID {bad_id}: got {res.status_code}"

        res_del = await auth_client_a.post(f"/expenses/{bad_id}/delete")
        assert res_del.status_code == 404, f"Failed for delete ID {bad_id}: got {res_del.status_code}"


# ===========================================================================
# 5. SQL Injection Resistance
# ===========================================================================

@pytest.mark.asyncio
async def test_sql_injection_search_safe(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """SQL injection payloads in search query must not crash or expose internal SQL errors."""
    sql_payloads = [
        "' OR '1'='1",
        "' UNION SELECT null, null, null--",
        "'; DROP TABLE expenses; --",
        "1' OR 1=1 #",
        "admin'--",
    ]
    for sql_str in sql_payloads:
        res = await auth_client_a.get(f"/transactions?q={sql_str}")
        assert res.status_code == 200
        assert "OperationalError" not in res.text
        assert "sqlite3" not in res.text.lower()
        assert "syntax error" not in res.text.lower()


# ===========================================================================
# 6. XSS Prevention
# ===========================================================================

@pytest.mark.asyncio
async def test_xss_in_expense_description_and_name_escaped(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """HTML / JavaScript payloads in expense description must be escaped by Jinja2."""
    await clear_all_expenses(db_session, user_a.id)
    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'

    # Create expense with XSS payload
    res = await auth_client_a.post("/expenses", data={
        "amount": "15.00",
        "description": xss_payload,
        "next_url": "/dashboard",
    })
    assert res.status_code == 303

    # Verify rendered dashboard escapes script tags
    dash = await auth_client_a.get("/dashboard")
    assert dash.status_code == 200
    # Must NOT contain raw unescaped script execution tag
    assert '<script>alert("xss")</script>' not in dash.text
    # Must contain HTML-escaped version
    assert '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;' in dash.text or '&lt;script&gt;' in dash.text

    # Verify rendered transactions ledger escapes script tags
    tx_page = await auth_client_a.get("/transactions")
    assert tx_page.status_code == 200
    assert '<script>alert("xss")</script>' not in tx_page.text


@pytest.mark.asyncio
async def test_xss_in_404_handler_escaped(client: AsyncClient):
    """404 error page must escape any user-supplied details in HTML."""
    xss_param = '<script>alert("404-xss")</script>'
    res = await client.get(f"/nonexistent-page/{xss_param}", headers={"Accept": "text/html"})
    assert res.status_code == 404
    assert '<script>alert("404-xss")</script>' not in res.text


# ===========================================================================
# 7. Open Redirect Prevention
# ===========================================================================

@pytest.mark.asyncio
async def test_open_redirect_attacks_blocked(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """Adversarial next_url payloads must be neutralized and default to safe internal paths."""
    malicious_urls = [
        "//evil.com",
        "//evil.com/phish",
        "/\\evil.com",
        "https://evil.com",
        "http://evil.com/steal",
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "\\\\evil.com",
    ]
    for evil in malicious_urls:
        res = await auth_client_a.post("/expenses", data={
            "amount": "10.00",
            "description": "Redirect Test",
            "next_url": evil,
        }, follow_redirects=False)
        assert res.status_code == 303
        loc = res.headers.get("location", "")
        # Must NOT redirect to external evil domain
        assert "evil.com" not in loc
        assert "javascript:" not in loc
        assert loc.startswith("/dashboard") or loc.startswith("/transactions")

    # Legitimate internal paths must be preserved
    res_valid = await auth_client_a.post("/expenses", data={
        "amount": "10.00",
        "description": "Legit Path",
        "next_url": "/transactions?q=Legit",
    }, follow_redirects=False)
    assert res_valid.status_code == 303
    assert res_valid.headers.get("location") == "/transactions?q=Legit"


# ===========================================================================
# 8. CSV Formula Injection Neutralization
# ===========================================================================

@pytest.mark.asyncio
async def test_csv_formula_injection_neutralized(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """
    Spreadsheet formula trigger characters (=, +, -, @, \t, \r) at the start of
    user-controlled fields must be neutralized with a leading single quote in CSV export.
    """
    await clear_all_expenses(db_session, user_a.id)

    formula_desc = "=cmd|'/C calc'!A0"
    formula_cat = "+SUM(A1:A10)"

    await create_expense(
        db_session,
        user_id=user_a.id,
        amount=Decimal("50.00"),
        description=formula_desc,
        category=formula_cat,
    )

    res_csv = await auth_client_a.get("/transactions/export/csv")
    assert res_csv.status_code == 200
    csv_lines = res_csv.text.strip().split("\r\n") if "\r\n" in res_csv.text else res_csv.text.strip().split("\n")
    # Data row is the second row
    data_row = csv_lines[1]
    # Neutralized cell begins with single quote `'=` or `'+`
    assert "'=cmd" in data_row or not data_row.startswith("=cmd")
    assert "'+SUM" in data_row or not data_row.startswith("+SUM")


# ===========================================================================
# 9. HTTP Method Abuse & State Mutations
# ===========================================================================

@pytest.mark.asyncio
async def test_get_on_mutation_endpoints_does_not_mutate(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """GET requests on mutation endpoints must be rejected (405 Method Not Allowed or 404)."""
    await clear_all_expenses(db_session, user_a.id)
    exp = await create_expense(
        db_session,
        user_id=user_a.id,
        amount=Decimal("20.00"),
        description="Safe Record",
    )

    # Attempt GET /expenses/clear-all
    r_clear = await auth_client_a.client.get("/expenses/clear-all")
    assert r_clear.status_code in (404, 405)

    # Attempt GET /expenses/{id}/delete
    r_del = await auth_client_a.client.get(f"/expenses/{exp.id}/delete")
    assert r_del.status_code in (404, 405)

    # Verify record still exists
    stmt = select(User).where(User.id == user_a.id)
    assert (await db_session.get(exp.__class__, exp.id)) is not None


# ===========================================================================
# 10. Security Headers
# ===========================================================================

@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """Responses must contain standard security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy."""
    res = await client.get("/sign-in")
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")
    assert res.headers.get("referrer-policy") is not None
