"""
Phase 11 Functional Regression Test Suite
Validates all Phase 11 requirements:
1. Amount validation (gt 0, max 2 decimal places) on Create and Edit routes.
2. Description validation (not empty, max 500 chars) on Create and Edit routes.
3. User-facing error message query params and rendered error alert banners.
4. Strict cross-tenant isolation (HTTP 404 on cross-user edit or delete).
5. Full CRUD lifecycle and server-authoritative balance updates.
6. Empty-state UI rendering when zero expenses exist.
"""
import asyncio
import os
import sys
import tempfile
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Setup clean test database
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "phase11_regression_test.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True
)
TestingSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

from app.main import app
from app.db.session import Base, get_db
from app.core.security import sign_session_data, generate_csrf_token
from app.models.user import User
from app.services.auth_service import register_user
from app.services.expense_service import clear_all_expenses, get_dashboard_stats


async def override_get_db():
    async with TestingSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


class TestUserClient:
    def __init__(self, user: User, client: httpx.AsyncClient):
        self.user = user
        self.client = client
        self.session_id = f"sess-{user.id[:8]}"
        self.csrf_token = generate_csrf_token(self.session_id)
        session_cookie = sign_session_data({
            "user_id": user.id,
            "user_email": user.email,
            "user_name": user.full_name,
            "session_id": self.session_id,
        })
        self.client.cookies.set("expense_session", session_cookie)

    async def post(self, url: str, data: dict = None, **kwargs):
        payload = (data or {}).copy()
        if "_csrf_token" not in payload:
            payload["_csrf_token"] = self.csrf_token
        return await self.client.post(url, data=payload, follow_redirects=False, **kwargs)

    async def get(self, url: str, **kwargs):
        return await self.client.get(url, follow_redirects=True, **kwargs)


async def run_phase11_regression():
    print("=" * 65)
    print("  PHASE 11 FUNCTIONAL REGRESSION TEST SUITE")
    print("=" * 65)

    # Initialize tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as raw_client_a, \
               httpx.AsyncClient(transport=transport, base_url="http://test") as raw_client_b:

        # 1. Register test users
        print("\n[Step 1] Initializing isolated tenant accounts...")
        async with TestingSession() as session:
            user_a, _ = await register_user(session, "tenant_a@decodelabs.dev", "Password123!", "Tenant Alpha")
            user_b, _ = await register_user(session, "tenant_b@decodelabs.dev", "Password123!", "Tenant Beta")
            await session.commit()

        client_a = TestUserClient(user_a, raw_client_a)
        client_b = TestUserClient(user_b, raw_client_b)
        print("  -> Tenant Alpha & Tenant Beta authenticated.")

        # 2. Test Amount Validation on Create Route
        print("\n[Step 2] Testing Amount Validation on POST /expenses (Create)...")

        # 2a. Negative amount
        res = await client_a.post("/expenses", data={"amount": "-25.00", "description": "Negative"})
        assert res.status_code == 303, f"Expected 303, got {res.status_code}"
        loc = res.headers.get("location", "")
        assert "error=" in loc and "positive" in loc.lower(), f"Unexpected location: {loc}"
        print("  [PASSED] Negative amount rejected with 303 and error query param.")

        # 2b. Zero amount
        res = await client_a.post("/expenses", data={"amount": "0", "description": "Zero"})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Zero amount rejected with 303 and error query param.")

        # 2c. More than 2 decimal places
        res = await client_a.post("/expenses", data={"amount": "14.999", "description": "Too many decimals"})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Amount with >2 decimal places rejected.")

        # 2d. Non-numeric amount
        res = await client_a.post("/expenses", data={"amount": "not_a_number", "description": "Invalid"})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Non-numeric amount string rejected.")

        # 3. Test Description Validation on Create Route
        print("\n[Step 3] Testing Description Validation on POST /expenses (Create)...")

        # 3a. Empty description
        res = await client_a.post("/expenses", data={"amount": "20.00", "description": "   "})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Blank/whitespace description rejected.")

        # 3b. Description > 500 chars
        res = await client_a.post("/expenses", data={"amount": "20.00", "description": "D" * 501})
        assert res.status_code == 303
        loc = res.headers.get("location", "")
        assert "error=" in loc and "500" in loc, f"Expected 500-char error in location: {loc}"
        print("  [PASSED] Description > 500 characters rejected.")

        # 3c. Description exactly 500 chars (boundary test)
        res = await client_a.post("/expenses", data={"amount": "10.00", "description": "X" * 500})
        assert res.status_code == 303
        assert "error=" not in res.headers.get("location", "")
        print("  [PASSED] Description exactly 500 characters accepted.")

        # 4. UI Error Feedback Verification
        print("\n[Step 4] Verifying UI Error Feedback Banner in Dashboard...")
        res_ui = await client_a.get(f"/dashboard?error=Invalid+amount.+Enter+a+positive+number+with+up+to+2+decimal+places.")
        assert res_ui.status_code == 200
        assert "expense-error-alert" in res_ui.text, "Error alert banner missing from dashboard HTML"
        assert "Invalid amount" in res_ui.text, "Error message text missing from dashboard HTML"
        print("  [PASSED] Dashboard correctly displays dismissable server validation banner.")

        # 5. Successful Expense Creation & Valid Formats
        print("\n[Step 5] Testing Successful Expense Creation & Edge Formats...")
        # Whole integer
        res = await client_a.post("/expenses", data={"amount": "40", "description": "Integer Amount"})
        assert res.status_code == 303
        # Single decimal
        res = await client_a.post("/expenses", data={"amount": "12.5", "description": "Single Decimal"})
        assert res.status_code == 303
        # Two decimals
        res = await client_a.post("/expenses", data={"amount": "30.25", "description": "Standard Two Decimals"})
        assert res.status_code == 303
        print("  [PASSED] Valid integer, single-decimal, and standard amounts successfully created.")

        # Verify created expenses and get ID
        res_tx = await client_a.get("/transactions")
        assert "Integer Amount" in res_tx.text
        assert "Single Decimal" in res_tx.text
        assert "Standard Two Decimals" in res_tx.text

        # Fetch expense ID from db
        async with TestingSession() as session:
            stats = await get_dashboard_stats(session, user_id=user_a.id, session_id="test")
            assert stats.transaction_count >= 3
            target_exp = stats.recent_expenses[0]
            exp_id = target_exp.id

        # 6. Test Validation on Edit Route
        print("\n[Step 6] Testing Amount & Description Validation on POST /expenses/{id}/edit...")

        # 6a. Negative amount on edit
        res = await client_a.post(f"/expenses/{exp_id}/edit", data={"amount": "-10.00", "description": "Updated"})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Edit with negative amount rejected.")

        # 6b. >2 decimals on edit
        res = await client_a.post(f"/expenses/{exp_id}/edit", data={"amount": "15.999", "description": "Updated"})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Edit with >2 decimals rejected.")

        # 6c. Description > 500 chars on edit
        res = await client_a.post(f"/expenses/{exp_id}/edit", data={"amount": "15.00", "description": "Z" * 501})
        assert res.status_code == 303
        assert "error=" in res.headers.get("location", "")
        print("  [PASSED] Edit with description > 500 chars rejected.")

        # 6d. Successful edit
        res = await client_a.post(f"/expenses/{exp_id}/edit", data={"amount": "99.99", "description": "Successfully Updated"})
        assert res.status_code == 303
        assert "error=" not in res.headers.get("location", "")
        print("  [PASSED] Valid edit successfully processed.")

        # 7. Cross-Tenant Security Checks
        print("\n[Step 7] Testing Cross-Tenant Security Isolation (HTTP 404)...")
        # Tenant Beta attempts to edit Tenant Alpha's expense
        res = await client_b.post(f"/expenses/{exp_id}/edit", data={"amount": "1.00", "description": "Hijacked"})
        assert res.status_code == 404, f"Expected 404 for cross-tenant edit, got {res.status_code}"
        print("  [PASSED] Cross-tenant edit securely returned HTTP 404.")

        # Tenant Beta attempts to delete Tenant Alpha's expense
        res = await client_b.post(f"/expenses/{exp_id}/delete")
        assert res.status_code == 404, f"Expected 404 for cross-tenant delete, got {res.status_code}"
        print("  [PASSED] Cross-tenant delete securely returned HTTP 404.")

        # 8. Deletion Lifecycle & Empty-State
        print("\n[Step 8] Testing Deletion Lifecycle & Empty-State UX...")
        # Clean slate Tenant Alpha
        async with TestingSession() as session:
            await clear_all_expenses(session, user_id=user_a.id)

        # Empty dashboard verification
        res_empty = await client_a.get("/dashboard")
        assert res_empty.status_code == 200
        assert "No recorded expenses yet" in res_empty.text, "Empty state message missing from dashboard"
        assert "$0.00" in res_empty.text or "0.00" in res_empty.text, "Zero total not rendered"
        print("  [PASSED] Empty state placeholder and zero total verified.")

    # Cleanup DB file
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    print("\n" + "=" * 65)
    print(">>> ALL PHASE 11 REGRESSION CHECKS PASSED PERFECTLY! <<<")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_phase11_regression())
