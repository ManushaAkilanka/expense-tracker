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


@pytest.mark.asyncio
async def test_expense_crud_and_running_balance(db_session: AsyncSession, user_a: User):
    # Ensure clean slate for hermetic test
    await clear_all_expenses(db_session, user_id=user_a.id)

    # 1. Create 3 expenses matching screenshot sequence: $25, $75, $50
    exp1 = await create_expense(db_session, user_id=user_a.id, amount=Decimal("25.00"), description="Domain Registration", category="Tools")
    exp2 = await create_expense(db_session, user_id=user_a.id, amount=Decimal("75.00"), description="Cloud Server", category="Infrastructure")
    exp3 = await create_expense(db_session, user_id=user_a.id, amount=Decimal("50.00"), description="API Gateway", category="Infrastructure")

    assert exp1.id is not None
    assert exp2.id is not None
    assert exp3.id is not None

    # 2. Verify running balance computation
    expenses = await get_user_expenses_with_balances(db_session, user_id=user_a.id)
    assert len(expenses) == 3

    # Reverse chronological check (newest first)
    # Newest is exp3 ($50.00), running balance should be 25 + 75 + 50 = $150.00
    assert expenses[0].id == exp3.id
    assert expenses[0].amount == Decimal("50.00")
    assert expenses[0].running_balance == Decimal("150.00")
    assert expenses[0].formatted_amount == "+Rs.50.00"
    assert expenses[0].formatted_running_balance == "Rs.150.00"

    # Second newest is exp2 ($75.00), running balance was 25 + 75 = $100.00
    assert expenses[1].id == exp2.id
    assert expenses[1].amount == Decimal("75.00")
    assert expenses[1].running_balance == Decimal("100.00")

    # Oldest is exp1 ($25.00), running balance was $25.00
    assert expenses[2].id == exp1.id
    assert expenses[2].amount == Decimal("25.00")
    assert expenses[2].running_balance == Decimal("25.00")

    # 3. Dashboard stats
    stats = await get_dashboard_stats(db_session, user_id=user_a.id, session_id="test-session")
    assert stats.total_spent == Decimal("150.00")
    assert stats.formatted_total_spent == "Rs.150.00"
    assert stats.transaction_count == 3

    # 4. Update expense
    updated = await update_expense(db_session, user_id=user_a.id, expense_id=exp1.id, amount=Decimal("35.00"), description="Updated Domain")
    assert updated is not None
    assert updated.amount == Decimal("35.00")
    assert updated.description == "Updated Domain"

    # Check new total is 35 + 75 + 50 = 160.00
    new_stats = await get_dashboard_stats(db_session, user_id=user_a.id, session_id="test-session")
    assert new_stats.total_spent == Decimal("160.00")

    # 5. Delete single expense
    deleted = await delete_expense(db_session, user_id=user_a.id, expense_id=exp2.id)
    assert deleted is True

    remaining = await get_user_expenses_with_balances(db_session, user_id=user_a.id)
    assert len(remaining) == 2

    # 6. Clear all expenses
    cleared_count = await clear_all_expenses(db_session, user_id=user_a.id)
    assert cleared_count == 2

    final_expenses = await get_user_expenses_with_balances(db_session, user_id=user_a.id)
    assert len(final_expenses) == 0
