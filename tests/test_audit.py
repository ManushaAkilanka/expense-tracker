from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.user import User
from app.services.expense_service import create_expense, update_expense, delete_expense


@pytest.mark.asyncio
async def test_audit_event_logging(db_session: AsyncSession, user_a: User):
    # Expense creation audit
    exp = await create_expense(db_session, user_id=user_a.id, amount=Decimal("45.00"), description="Audit Test Expense")

    stmt = select(AuditEvent).where(AuditEvent.user_id == user_a.id, AuditEvent.event_type == "EXPENSE_CREATED")
    res = await db_session.execute(stmt)
    event = res.scalar_one_or_none()
    assert event is not None
    assert event.amount == Decimal("45.00")
    assert event.expense_id == exp.id

    # Expense update audit
    await update_expense(db_session, user_id=user_a.id, expense_id=exp.id, amount=Decimal("55.00"))
    stmt_up = select(AuditEvent).where(AuditEvent.user_id == user_a.id, AuditEvent.event_type == "EXPENSE_UPDATED")
    res_up = await db_session.execute(stmt_up)
    event_up = res_up.scalar_one_or_none()
    assert event_up is not None
    assert event_up.amount == Decimal("55.00")

    # Expense delete audit
    await delete_expense(db_session, user_id=user_a.id, expense_id=exp.id)
    stmt_del = select(AuditEvent).where(AuditEvent.user_id == user_a.id, AuditEvent.event_type == "EXPENSE_DELETED")
    res_del = await db_session.execute(stmt_del)
    event_del = res_del.scalar_one_or_none()
    assert event_del is not None
