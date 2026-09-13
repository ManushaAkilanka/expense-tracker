from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.core.session import get_session
from app.core.security import verify_csrf_token
from app.models.user import User


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Retrieve currently authenticated user or None if unauthenticated."""
    session = get_session(request)
    user_id = session.get("user_id")
    if not user_id:
        return None

    stmt = select(User).where(User.id == user_id, User.is_active == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    return user


async def get_current_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Ensure user is authenticated. Redirects to /sign-in if HTML or general request, or 401 if API."""
    if not user:
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header or "*/*" in accept_header or not accept_header:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"/sign-in?next={request.url.path}"}
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


async def require_csrf(request: Request) -> None:
    """Validate CSRF token for state-changing POST/PUT/DELETE requests."""
    session = get_session(request)
    session_id = session.get("session_id", "")

    # Check form body or header
    token = None
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        token = form.get("_csrf_token")
    if not token:
        token = request.headers.get("X-CSRF-Token")

    if not token or not verify_csrf_token(str(token), session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired CSRF token. Please refresh the page and try again."
        )
