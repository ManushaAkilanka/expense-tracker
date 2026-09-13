from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.expense_service import (
    create_expense,
    get_user_expenses_with_balances,
    get_expense_by_id,
    update_expense,
    delete_expense,
    clear_all_expenses,
    get_dashboard_stats,
)
from tests.conftest import AuthenticatedSessionClient


@pytest.mark.asyncio
async def test_strict_multi_tenant_isolation(
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    auth_client_a: AuthenticatedSessionClient,
    auth_client_b: AuthenticatedSessionClient,
):
    # Ensure clean slate for hermetic isolation
    await clear_all_expenses(db_session, user_id=user_a.id)
    await clear_all_expenses(db_session, user_id=user_b.id)

    # 1. User A creates 2 expenses
    exp_a1 = await create_expense(db_session, user_id=user_a.id, amount=Decimal("100.00"), description="User A Secret Server")
    exp_a2 = await create_expense(db_session, user_id=user_a.id, amount=Decimal("50.00"), description="User A Secret Database")

    # User B creates 1 expense
    exp_b1 = await create_expense(db_session, user_id=user_b.id, amount=Decimal("20.00"), description="User B Public Tool")

    # 2. Verify User A only sees their own expenses ($150 total, 2 items)
    expenses_a = await get_user_expenses_with_balances(db_session, user_id=user_a.id)
    assert len(expenses_a) == 2
    assert all(e.user_id == user_a.id for e in expenses_a)
    stats_a = await get_dashboard_stats(db_session, user_id=user_a.id, session_id="session-a")
    assert stats_a.total_spent == Decimal("150.00")
    assert stats_a.transaction_count == 2

    # 3. Verify User B only sees their own expenses ($20 total, 1 item)
    expenses_b = await get_user_expenses_with_balances(db_session, user_id=user_b.id)
    assert len(expenses_b) == 1
    assert expenses_b[0].id == exp_b1.id
    assert expenses_b[0].user_id == user_b.id
    stats_b = await get_dashboard_stats(db_session, user_id=user_b.id, session_id="session-b")
    assert stats_b.total_spent == Decimal("20.00")
    assert stats_b.transaction_count == 1

    # 4. Direct service isolation checks:
    # User B cannot get User A's expense by ID
    forbidden_get = await get_expense_by_id(db_session, user_id=user_b.id, expense_id=exp_a1.id)
    assert forbidden_get is None

    # User B cannot update User A's expense
    forbidden_update = await update_expense(db_session, user_id=user_b.id, expense_id=exp_a1.id, amount=Decimal("1.00"))
    assert forbidden_update is None

    # User B cannot delete User A's expense
    forbidden_delete = await delete_expense(db_session, user_id=user_b.id, expense_id=exp_a1.id)
    assert forbidden_delete is False

    # 5. HTTP Level Isolation Checks:
    # User B attempts to delete User A's expense via POST /expenses/{id}/delete -> 404
    del_res = await auth_client_b.post(f"/expenses/{exp_a1.id}/delete")
    assert del_res.status_code == 404

    # User B attempts to edit User A's expense via POST /expenses/{id}/edit -> 404
    edit_res = await auth_client_b.post(f"/expenses/{exp_a1.id}/edit", data={"amount": "5.00", "description": "Hacked"})
    assert edit_res.status_code == 404

    # 6. Export Isolation:
    # User B's CSV export must only have User B's data
    csv_res = await auth_client_b.get("/transactions/export/csv")
    assert csv_res.status_code == 200
    csv_text = csv_res.text
    assert "User B Public Tool" in csv_text
    assert "User A Secret Server" not in csv_text
    assert "User A Secret Database" not in csv_text
