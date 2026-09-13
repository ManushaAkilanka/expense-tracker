from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user, require_csrf
from app.core.security import safe_redirect_target
from app.models.user import User
from app.services.expense_service import (
    create_expense,
    update_expense,
    delete_expense,
    clear_all_expenses,
)

MAX_DESCRIPTION_LENGTH = 500

router = APIRouter(prefix="/expenses", tags=["Expenses"])


@router.post("")
async def handle_create_expense(
    request: Request,
    amount: str = Form(...),
    description: str = Form(...),
    category: str = Form("General"),
    currency: str = Form("LKR"),
    next_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    redirect_target = safe_redirect_target(next_url, default="/dashboard")

    # --- Validate amount ---
    try:
        cleaned_amount_str = amount.replace("Rs.", "").replace("Rs", "").replace("LKR", "").replace("$", "").replace(",", "").strip()
        parsed_amount = Decimal(cleaned_amount_str)
        if parsed_amount <= 0:
            raise ValueError("Amount must be positive.")
        if parsed_amount.quantize(Decimal('0.01')) != parsed_amount:
            raise ValueError("Amount must have at most two decimal places.")
    except (InvalidOperation, ValueError):
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": "Invalid amount. Enter a positive number with up to 2 decimal places."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # --- Validate description ---
    if not description or not description.strip():
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": "Description cannot be empty."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if len(description.strip()) > MAX_DESCRIPTION_LENGTH:
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await create_expense(
        db=db,
        user_id=current_user.id,
        amount=parsed_amount,
        description=description,
        category=category,
        currency=currency,
    )

    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{expense_id}/edit")
async def handle_update_expense(
    request: Request,
    expense_id: str,
    amount: str = Form(...),
    description: str = Form(...),
    category: Optional[str] = Form("General"),
    next_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    redirect_target = safe_redirect_target(next_url, default="/transactions")

    # --- Validate amount ---
    try:
        cleaned_amount_str = amount.replace("Rs.", "").replace("Rs", "").replace("LKR", "").replace("$", "").replace(",", "").strip()
        parsed_amount = Decimal(cleaned_amount_str)
        if parsed_amount <= 0:
            raise ValueError("Amount must be positive.")
        if parsed_amount.quantize(Decimal('0.01')) != parsed_amount:
            raise ValueError("Amount must have at most two decimal places.")
    except (InvalidOperation, ValueError):
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": "Invalid amount. Enter a positive number with up to 2 decimal places."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # --- Validate description ---
    if not description or not description.strip():
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": "Description cannot be empty."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if len(description.strip()) > MAX_DESCRIPTION_LENGTH:
        return RedirectResponse(
            url=f"{redirect_target}?" + urlencode({"error": f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    updated = await update_expense(
        db=db,
        user_id=current_user.id,
        expense_id=expense_id,
        amount=parsed_amount,
        description=description,
        category=category or "General",
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense record not found or unauthorized access."
        )

    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{expense_id}/delete")
async def handle_delete_expense(
    request: Request,
    expense_id: str,
    next_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    deleted = await delete_expense(db=db, user_id=current_user.id, expense_id=expense_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense record not found or unauthorized access."
        )

    redirect_target = safe_redirect_target(next_url, default="/dashboard")
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/clear-all")
async def handle_clear_all_expenses(
    request: Request,
    next_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    await clear_all_expenses(db=db, user_id=current_user.id)
    redirect_target = safe_redirect_target(next_url, default="/dashboard")
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)
