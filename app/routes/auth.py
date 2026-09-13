import re
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_db, get_current_user_optional, require_csrf
from app.core.oauth import get_oauth_client
from app.core.security import safe_redirect_target
from app.core.session import get_session, mark_session_modified, clear_session
from app.models.user import User
from app.services.auth_service import register_user, authenticate_user, handle_oauth_user
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/sign-in", response_class=HTMLResponse)
async def sign_in_page(
    request: Request,
    next: Optional[str] = None,
    error: Optional[str] = None,
    message: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/sign_in.html",
        context={
            "next_url": safe_redirect_target(next, default="/dashboard"),
            "csrf_token": request.state.csrf_token,
            "google_enabled": settings.is_google_oauth_configured,
            "error": error,
            "message": message,
        },
    )


@router.post("/sign-in")
async def sign_in(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    clean_email = email.strip().lower() if email else ""
    if not clean_email or not password:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_in.html",
            context={
                "email": clean_email,
                "next_url": next_url or "/dashboard",
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Invalid email or password.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user, error = await authenticate_user(db, email=clean_email, password=password)
    if error or not user:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_in.html",
            context={
                "email": clean_email,
                "next_url": next_url or "/dashboard",
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": error or "Invalid email or password.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    session = get_session(request)
    session["session_id"] = str(uuid.uuid4())  # Rotate session ID on authentication
    session["user_id"] = user.id
    session["user_email"] = user.email
    session["user_name"] = user.full_name
    mark_session_modified(request)

    redirect_target = safe_redirect_target(next_url, default="/dashboard")
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/sign-up", response_class=HTMLResponse)
async def sign_up_page(
    request: Request,
    error: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/sign_up.html",
        context={
            "csrf_token": request.state.csrf_token,
            "google_enabled": settings.is_google_oauth_configured,
            "error": error,
        },
    )


@router.post("/sign-up")
async def sign_up(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    clean_name = full_name.strip() if full_name else ""
    clean_email = email.strip().lower() if email else ""

    if not clean_name:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": full_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Please provide your full name.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not clean_email or not EMAIL_REGEX.match(clean_email):
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": clean_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Please provide a valid email address.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not password:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": clean_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Password cannot be empty.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": clean_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Passwords do not match.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": clean_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "Password must be at least 8 characters.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user, error = await register_user(
        db,
        email=clean_email,
        password=password,
        full_name=clean_name,
    )
    if error or not user:
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_up.html",
            context={
                "full_name": clean_name,
                "email": clean_email,
                "csrf_token": request.state.csrf_token,
                "google_enabled": settings.is_google_oauth_configured,
                "error": "This email is already registered." if "already exists" in (error or "") else (error or "Could not create account."),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Establish session with freshly generated session_id
    session = get_session(request)
    session["session_id"] = str(uuid.uuid4())
    session["user_id"] = user.id
    session["user_email"] = user.email
    session["user_name"] = user.full_name
    mark_session_modified(request)

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/google")
async def auth_google(request: Request):
    """Initiate Google OAuth flow with graceful fallback if unconfigured."""
    oauth = get_oauth_client()
    if not settings.is_google_oauth_configured or not oauth or not hasattr(oauth, "google"):
        return templates.TemplateResponse(
            request=request,
            name="auth/sign_in.html",
            context={
                "next_url": "/dashboard",
                "csrf_token": request.state.csrf_token,
                "google_enabled": False,
                "error": "Google OAuth credentials are not configured on this server. Please sign in with email and password.",
            },
            status_code=status.HTTP_200_OK,
        )

    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def auth_google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback."""
    oauth = get_oauth_client()
    if not settings.is_google_oauth_configured or not oauth or not hasattr(oauth, "google"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured."
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authorization failed: {str(e)}"
        )

    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.google.userinfo(token=token)

    google_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name", "")
    picture = user_info.get("picture")

    if not google_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete user profile received from Google."
        )

    user = await handle_oauth_user(
        db=db,
        provider="google",
        provider_account_id=google_id,
        email=email,
        full_name=name,
        avatar_url=picture,
    )

    session = get_session(request)
    session["session_id"] = str(uuid.uuid4())
    session["user_id"] = user.id
    session["user_email"] = user.email
    session["user_name"] = user.full_name
    mark_session_modified(request)

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    if current_user:
        await log_audit_event(
            db=db,
            user_id=current_user.id,
            event_type="USER_SIGNED_OUT"
        )
        await db.commit()

    clear_session(request)
    return RedirectResponse(url="/sign-in", status_code=status.HTTP_303_SEE_OTHER)
