from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.models.user import User
from app.services.expense_service import get_user_expenses_with_balances, format_currency
from app.services.export_service import generate_csv_data, generate_json_data

router = APIRouter(prefix="/transactions", tags=["Transactions"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    q: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    expenses = await get_user_expenses_with_balances(
        db=db,
        user_id=current_user.id,
        search_query=q
    )

    # Compute aggregate stats for top cards
    total_spent = sum((e.amount for e in expenses), Decimal("0.00"))
    total_count = len(expenses)

    return templates.TemplateResponse(
        request=request,
        name="transactions/index.html",
        context={
            "user": current_user,
            "expenses": expenses,
            "search_query": q or "",
            "total_spent": total_spent,
            "formatted_total_spent": format_currency(total_spent),
            "total_count": total_count,
            "csrf_token": request.state.csrf_token,
            "active_tab": "transactions",
            "error": error or "",
        },
    )


@router.get("/export/csv")
async def export_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    expenses = await get_user_expenses_with_balances(db=db, user_id=current_user.id)
    csv_data = generate_csv_data(expenses)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'}
    )


@router.get("/export/json")
async def export_json(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    expenses = await get_user_expenses_with_balances(db=db, user_id=current_user.id)
    json_data = generate_json_data(expenses)
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="transactions.json"'}
    )
