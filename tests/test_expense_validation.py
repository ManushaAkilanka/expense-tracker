"""Phase 11 – Expense CRUD validation and edge-case regression tests."""
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.expense_service import (
    create_expense,
    get_user_expenses_with_balances,
    update_expense,
    delete_expense,
    clear_all_expenses,
    get_dashboard_stats,
)
from tests.conftest import AuthenticatedSessionClient


# ---------------------------------------------------------------------------
# Helper: ensure a clean slate for deterministic tests
# ---------------------------------------------------------------------------
async def _clean_slate(db: AsyncSession, *user_ids: str):
    for uid in user_ids:
        await clear_all_expenses(db, user_id=uid)


# ===========================================================================
# 1.  Amount validation – Create route (HTTP level)
# ===========================================================================

@pytest.mark.asyncio
async def test_create_negative_amount_returns_redirect(auth_client_a: AuthenticatedSessionClient):
    """Negative amount should redirect back with an error query param."""
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "-50.00", "description": "Bad expense", "next_url": "/dashboard"},
    )
    # Validation redirects (303) back to dashboard with ?error=...
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_zero_amount_returns_redirect(auth_client_a: AuthenticatedSessionClient):
    """Zero amount should redirect back with an error query param."""
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "0", "description": "Zero", "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_too_many_decimals_returns_redirect(auth_client_a: AuthenticatedSessionClient):
    """Amount with 3+ decimal places should redirect back with an error."""
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "12.345", "description": "Precise", "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_non_numeric_amount_returns_redirect(auth_client_a: AuthenticatedSessionClient):
    """Non-numeric amount should redirect back with an error."""
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "abc", "description": "Text amount", "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_description_too_long_returns_redirect(auth_client_a: AuthenticatedSessionClient):
    """Description > 500 chars should redirect back with an error."""
    long_desc = "A" * 501
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "10.00", "description": long_desc, "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


# ===========================================================================
# 2.  Amount validation – Edit route (HTTP level)
# ===========================================================================

@pytest.mark.asyncio
async def test_edit_negative_amount_returns_redirect(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """Edit with a negative amount should redirect back with error."""
    await _clean_slate(db_session, user_a.id)
    exp = await create_expense(db_session, user_id=user_a.id, amount=Decimal("20.00"), description="Editable")
    res = await auth_client_a.post(
        f"/expenses/{exp.id}/edit",
        data={"amount": "-5.00", "description": "Hacked", "next_url": "/transactions"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_edit_too_many_decimals_returns_redirect(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """Edit with 3+ decimal places should redirect with error."""
    await _clean_slate(db_session, user_a.id)
    exp = await create_expense(db_session, user_id=user_a.id, amount=Decimal("20.00"), description="Editable2")
    res = await auth_client_a.post(
        f"/expenses/{exp.id}/edit",
        data={"amount": "9.999", "description": "TooManyDecimals", "next_url": "/transactions"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_edit_description_too_long_returns_redirect(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """Edit with description > 500 chars should redirect with error."""
    await _clean_slate(db_session, user_a.id)
    exp = await create_expense(db_session, user_id=user_a.id, amount=Decimal("20.00"), description="Editable3")
    long_desc = "B" * 501
    res = await auth_client_a.post(
        f"/expenses/{exp.id}/edit",
        data={"amount": "20.00", "description": long_desc, "next_url": "/transactions"},
    )
    assert res.status_code == 303
    assert "error=" in res.headers.get("location", "")


# ===========================================================================
# 3.  Cross-tenant isolation (HTTP level) – update and delete → 404
# ===========================================================================

@pytest.mark.asyncio
async def test_cross_tenant_edit_returns_404(
    db_session: AsyncSession, user_a: User, user_b: User,
    auth_client_a: AuthenticatedSessionClient, auth_client_b: AuthenticatedSessionClient,
):
    """User B editing User A's expense should get 404, not 403."""
    await _clean_slate(db_session, user_a.id, user_b.id)
    exp_a = await create_expense(db_session, user_id=user_a.id, amount=Decimal("50.00"), description="A's secret")
    res = await auth_client_b.post(
        f"/expenses/{exp_a.id}/edit",
        data={"amount": "1.00", "description": "Stolen"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_delete_returns_404(
    db_session: AsyncSession, user_a: User, user_b: User,
    auth_client_a: AuthenticatedSessionClient, auth_client_b: AuthenticatedSessionClient,
):
    """User B deleting User A's expense should get 404."""
    await _clean_slate(db_session, user_a.id, user_b.id)
    exp_a = await create_expense(db_session, user_id=user_a.id, amount=Decimal("30.00"), description="A's private")
    res = await auth_client_b.post(f"/expenses/{exp_a.id}/delete")
    assert res.status_code == 404


# ===========================================================================
# 4.  Successful CRUD lifecycle (HTTP level)
# ===========================================================================

@pytest.mark.asyncio
async def test_successful_create_edit_delete_lifecycle(
    auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User
):
    """End-to-end lifecycle: create → edit → verify total → delete."""
    await _clean_slate(db_session, user_a.id)

    # Create
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "100.00", "description": "Lifecycle Test", "next_url": "/dashboard"},
    )
    assert res.status_code == 303  # redirect on success

    # Verify creation via service layer
    expenses = await get_user_expenses_with_balances(db_session, user_id=user_a.id)
    assert len(expenses) >= 1
    created_exp = next((e for e in expenses if e.description == "Lifecycle Test"), None)
    assert created_exp is not None
    assert created_exp.amount == Decimal("100.00")

    # Edit
    res = await auth_client_a.post(
        f"/expenses/{created_exp.id}/edit",
        data={"amount": "200.00", "description": "Lifecycle Updated", "next_url": "/transactions"},
    )
    assert res.status_code == 303

    # Delete
    res = await auth_client_a.post(f"/expenses/{created_exp.id}/delete")
    assert res.status_code == 303


# ===========================================================================
# 5.  Empty-state dashboard (service layer)
# ===========================================================================

@pytest.mark.asyncio
async def test_empty_dashboard_stats(db_session: AsyncSession, user_a: User):
    """Dashboard stats should show zero totals when no expenses exist."""
    await _clean_slate(db_session, user_a.id)
    stats = await get_dashboard_stats(db_session, user_id=user_a.id, session_id="test-empty")
    assert stats.total_spent == Decimal("0.00")
    assert stats.transaction_count == 0
    assert stats.recent_expenses == []


# ===========================================================================
# 6.  Valid amount edge cases (should succeed)
# ===========================================================================

@pytest.mark.asyncio
async def test_create_valid_integer_amount(auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User):
    """Whole number like '42' should be accepted (0 decimal places is fine)."""
    await _clean_slate(db_session, user_a.id)
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "42", "description": "Whole number", "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" not in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_valid_one_decimal(auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User):
    """One decimal place like '9.5' should be accepted."""
    await _clean_slate(db_session, user_a.id)
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "9.5", "description": "One decimal", "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" not in res.headers.get("location", "")


@pytest.mark.asyncio
async def test_create_description_exactly_500_chars(auth_client_a: AuthenticatedSessionClient, db_session: AsyncSession, user_a: User):
    """Description at exactly 500 chars should be accepted."""
    await _clean_slate(db_session, user_a.id)
    desc = "C" * 500
    res = await auth_client_a.post(
        "/expenses",
        data={"amount": "5.00", "description": desc, "next_url": "/dashboard"},
    )
    assert res.status_code == 303
    assert "error=" not in res.headers.get("location", "")
