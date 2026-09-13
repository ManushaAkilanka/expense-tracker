import hmac
import hashlib
import secrets
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

# Initialize Argon2 Password Hasher with production-ready parameters
pwd_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=102400,  # 100 MiB
    parallelism=8,
    hash_len=32,
    salt_len=16
)

# Cookie / Session Serializer
serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session-salt")


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return pwd_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against an Argon2 hash."""
    if not hashed_password:
        return False
    try:
        return pwd_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_csrf_token(session_id: str) -> str:
    """Generate a HMAC-SHA256 CSRF token tied to a session ID."""
    message = f"{session_id}:{settings.SECRET_KEY}"
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{signature[:32]}"


def verify_csrf_token(token: str, session_id: str) -> bool:
    """Verify a CSRF token matches the expected signature for this session."""
    if not token or not session_id:
        return False
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(token, expected)


def sign_session_data(data: dict) -> str:
    """Sign and encode session dictionary into a secure string."""
    return serializer.dumps(data)


def unsign_session_data(token: str, max_age: Optional[int] = None) -> Optional[dict]:
    """Unsign and decode session token. Returns None if invalid or expired."""
    if not token:
        return None
    try:
        data = serializer.loads(token, max_age=max_age or settings.SESSION_MAX_AGE)
        return data
    except (BadSignature, SignatureExpired):
        return None


def safe_redirect_target(url: Optional[str], default: str = "/dashboard") -> str:
    """
    Validate that a redirect target is a safe internal path on the same origin.
    Prevents open redirects via protocol-relative URLs (//evil.com),
    backslash tricks (/\\evil.com, \\evil.com), external schemes (https://evil.com),
    and javascript: schemes.
    """
    if not url:
        return default
    target = url.strip()
    if not target.startswith("/") or target.startswith("//") or target.startswith("/\\") or target.startswith("\\"):
        return default
    import urllib.parse
    try:
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme or parsed.netloc:
            return default
    except Exception:
        return default
    return target

