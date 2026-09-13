from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, select

from app.models.expense import Expense
from app.schemas.expense import ExpenseWithRunningBalance, DashboardStats
from app.services.audit_service import log_audit_event


def format_currency(amount: Decimal, currency: str = "LKR") -> str:
    """Format decimal amount according to currency."""
    if currency in ("USD", "$"):
        return f"${amount:,.2f}"
    return f"Rs.{amount:,.2f}"


async def create_expense(
    db: AsyncSession,
    user_id: str,
    amount: Decimal,
    description: str,
    category: str = "General",
    currency: str = "LKR",
) -> Expense:
    """Create a new expense for a user and log audit event."""
    clean_currency = currency.strip() if currency and currency.strip() else "LKR"
    expense = Expense(
        user_id=user_id,
        amount=amount,
        description=description.strip(),
        category=category.strip(),
        currency=clean_currency,
        created_at=datetime.now(timezone.utc),
    )
    db.add(expense)
    await db.flush()

    await log_audit_event(
        db=db,
        user_id=user_id,
        expense_id=expense.id,
        event_type="EXPENSE_CREATED",
        amount=amount,
        metadata={"description": expense.description, "category": expense.category}
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def get_user_expenses_with_balances(
    db: AsyncSession,
    user_id: str,
    search_query: Optional[str] = None,
) -> List[ExpenseWithRunningBalance]:
    """
    Retrieve all expenses for a user ordered chronologically to compute running balances,
    then return list reverse-chronologically with deterministic sequence numbers.
    Strictly isolated to user_id.
    """
    # 1. Fetch all expenses for this user in chronological order (ASC)
    stmt = (
        select(Expense)
        .where(Expense.user_id == user_id)
        .order_by(Expense.created_at.asc(), Expense.id.asc())
    )
    result = await db.execute(stmt)
    all_expenses = result.scalars().all()

    # 2. Compute cumulative running balances and sequence numbers
    running_total = Decimal("0.00")
    enriched: List[ExpenseWithRunningBalance] = []

    for index, exp in enumerate(all_expenses, start=1):
        running_total += exp.amount
        tx_code = f"#TX-{100 + index}"
        curr = exp.currency.strip().upper() if exp.currency else "LKR"
        prefix = "$" if curr in ("USD", "$") else "Rs."
        item = ExpenseWithRunningBalance(
            id=exp.id,
            user_id=exp.user_id,
            amount=exp.amount,
            currency=exp.currency,
            description=exp.description,
            category=exp.category,
            created_at=exp.created_at,
            updated_at=exp.updated_at,
            sequence_number=index,
            running_balance=running_total,
            formatted_amount=f"+{prefix}{exp.amount:,.2f}",
            formatted_running_balance=f"{prefix}{running_total:,.2f}",
            tx_code=tx_code,
        )
        enriched.append(item)

    # 3. Filter if search_query is supplied
    if search_query and search_query.strip():
        q = search_query.strip().lower()
        enriched = [
            e for e in enriched
            if q in e.description.lower()
            or q in e.category.lower()
            or q in str(e.amount)
            or q in e.tx_code.lower()
        ]

    # 4. Return in reverse chronological order (newest first)
    enriched.reverse()
    return enriched


async def get_expense_by_id(
    db: AsyncSession,
    user_id: str,
    expense_id: str,
) -> Optional[Expense]:
    """Retrieve single expense with strict user_id isolation."""
    stmt = select(Expense).where(
        Expense.id == expense_id,
        Expense.user_id == user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_expense(
    db: AsyncSession,
    user_id: str,
    expense_id: str,
    amount: Optional[Decimal] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[Expense]:
    """Update existing expense with strict user isolation."""
    expense = await get_expense_by_id(db, user_id=user_id, expense_id=expense_id)
    if not expense:
        return None

    old_amount = expense.amount
    if amount is not None:
        expense.amount = amount
    if description is not None:
        expense.description = description.strip()
    if category is not None:
        expense.category = category.strip()
    expense.updated_at = datetime.now(timezone.utc)

    await log_audit_event(
        db=db,
        user_id=user_id,
        expense_id=expense.id,
        event_type="EXPENSE_UPDATED",
        amount=expense.amount,
        metadata={"old_amount": str(old_amount), "new_amount": str(expense.amount)}
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def delete_expense(
    db: AsyncSession,
    user_id: str,
    expense_id: str,
) -> bool:
    """Delete an expense with strict user isolation."""
    expense = await get_expense_by_id(db, user_id=user_id, expense_id=expense_id)
    if not expense:
        return False

    deleted_amount = expense.amount
    deleted_desc = expense.description
    await db.delete(expense)

    await log_audit_event(
        db=db,
        user_id=user_id,
        expense_id=None,
        event_type="EXPENSE_DELETED",
        amount=deleted_amount,
        metadata={"deleted_id": expense_id, "description": deleted_desc}
    )
    await db.commit()
    return True


async def clear_all_expenses(
    db: AsyncSession,
    user_id: str,
) -> int:
    """Clear all expenses strictly for the specified user."""
    count_stmt = select(func.count(Expense.id)).where(Expense.user_id == user_id)
    total_count = (await db.execute(count_stmt)).scalar() or 0

    delete_stmt = delete(Expense).where(Expense.user_id == user_id)
    await db.execute(delete_stmt)

    await log_audit_event(
        db=db,
        user_id=user_id,
        event_type="EXPENSES_CLEARED",
        metadata={"cleared_count": total_count}
    )
    await db.commit()
    return total_count


async def get_dashboard_stats(
    db: AsyncSession,
    user_id: str,
    session_id: str,
) -> DashboardStats:
    """Calculate server-authoritative aggregate metrics for user's dashboard."""
    # Sum & count
    agg_stmt = (
        select(
            func.coalesce(func.sum(Expense.amount), Decimal("0.00")),
            func.count(Expense.id)
        )
        .where(Expense.user_id == user_id)
    )
    res = await db.execute(agg_stmt)
    total_spent, count = res.one()

    # Get recent expenses (up to 5, reverse chronological)
    enriched_expenses = await get_user_expenses_with_balances(db, user_id=user_id)
    recent = enriched_expenses[:5]

    # Determine currency from recent expenses or default LKR
    currency = enriched_expenses[0].currency if enriched_expenses else "LKR"
    prefix = "$" if currency.strip().upper() in ("USD", "$") else "Rs."

    short_session_id = f"#PY-{abs(hash(session_id)) % 9000 + 1000}"

    return DashboardStats(
        total_spent=total_spent,
        formatted_total_spent=f"{prefix}{total_spent:,.2f}",
        transaction_count=count,
        currency=currency,
        session_id=short_session_id,
        memory_state="Persistent",
        data_structure="list[float]",
        recent_expenses=recent,
    )
