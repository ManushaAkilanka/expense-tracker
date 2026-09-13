import time
import uuid
from typing import Any, Dict, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.core.security import sign_session_data, unsign_session_data, generate_csrf_token

# In-memory revoked session store: maps session_id -> timestamp
_REVOKED_SESSIONS: Dict[str, float] = {}


def revoke_session_id(session_id: str) -> None:
    """Revoke a session ID so replaying its signed cookie is rejected."""
    if session_id:
        _REVOKED_SESSIONS[session_id] = time.time()
        # Clean up entries older than max session age when table grows
        if len(_REVOKED_SESSIONS) > 2000:
            cutoff = time.time() - settings.SESSION_MAX_AGE
            keys_to_purge = [k for k, t in _REVOKED_SESSIONS.items() if t < cutoff]
            for k in keys_to_purge:
                _REVOKED_SESSIONS.pop(k, None)


def is_session_id_revoked(session_id: Optional[str]) -> bool:
    """Check if session_id has been explicitly revoked."""
    if not session_id:
        return False
    return session_id in _REVOKED_SESSIONS


class SessionMiddleware(BaseHTTPMiddleware):
    """Custom Session Middleware handling signed cookies, CSRF tokens, and session invalidation."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
        session_data: Dict[str, Any] = {}
        is_new_session = True

        if raw_cookie:
            decoded = unsign_session_data(raw_cookie)
            if isinstance(decoded, dict):
                sess_id = decoded.get("session_id")
                # Reject replayed cookie if session_id was revoked upon logout
                if sess_id and not is_session_id_revoked(sess_id):
                    session_data = decoded
                    is_new_session = False

        # Ensure session_id exists; if it had to be created, treat as new session
        if "session_id" not in session_data:
            session_data["session_id"] = str(uuid.uuid4())
            is_new_session = True

        request.state.session = session_data
        request.state.csrf_token = generate_csrf_token(session_data["session_id"])

        response = await call_next(request)

        session_cleared = getattr(request.state, "session_cleared", False)
        session_modified = getattr(request.state, "session_modified", False)

        if session_cleared:
            response.delete_cookie(
                key=settings.SESSION_COOKIE_NAME,
                path="/",
                httponly=True,
                samesite="lax",
                secure=settings.SECURE_COOKIE
            )
        elif session_modified or is_new_session:
            # Persist the cookie for new sessions (so CSRF tokens survive GET→POST)
            # and any explicitly modified sessions (login, etc.)
            signed = sign_session_data(request.state.session)
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=signed,
                max_age=settings.SESSION_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
                secure=settings.SECURE_COOKIE
            )

        return response


def get_session(request: Request) -> Dict[str, Any]:
    """Retrieve the current session dictionary from request state."""
    if not hasattr(request.state, "session"):
        request.state.session = {"session_id": str(uuid.uuid4())}
    return request.state.session


def mark_session_modified(request: Request) -> None:
    """Mark the session as modified so the response updates the cookie."""
    request.state.session_modified = True


def clear_session(request: Request) -> None:
    """Clear session data, revoke current session_id, and instruct middleware to delete cookie."""
    if hasattr(request.state, "session"):
        old_session_id = request.state.session.get("session_id")
        if old_session_id:
            revoke_session_id(old_session_id)
    request.state.session = {"session_id": str(uuid.uuid4())}
    request.state.session_cleared = True

