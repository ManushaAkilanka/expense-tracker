from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user, get_current_user_optional
from app.core.session import get_session
from app.models.user import User
from app.services.expense_service import get_dashboard_stats

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def root_redirect(
    current_user: User = Depends(get_current_user_optional)
):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/sign-in", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    error: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = get_session(request)
    session_id = session.get("session_id", "PY-4920")

    stats = await get_dashboard_stats(db, user_id=current_user.id, session_id=session_id)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "user": current_user,
            "stats": stats,
            "csrf_token": request.state.csrf_token,
            "active_tab": "dashboard",
            "error": error or "",
        },
    )
