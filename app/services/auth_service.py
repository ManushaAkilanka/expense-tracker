from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.user import User, OAuthAccount
from app.services.audit_service import log_audit_event


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
) -> Tuple[Optional[User], Optional[str]]:
    """Register a new email/password user."""
    normalized_email = email.strip().lower()

    # Check for existing user
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return None, "An account with this email address already exists."

    hashed_pw = hash_password(password)
    user = User(
        email=normalized_email,
        password_hash=hashed_pw,
        full_name=full_name.strip(),
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()

    # Log audit event
    await log_audit_event(
        db=db,
        user_id=user.id,
        event_type="USER_SIGNED_UP",
        metadata={"method": "email_password", "email": normalized_email}
    )
    await db.commit()
    await db.refresh(user)
    return user, None


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Tuple[Optional[User], Optional[str]]:
    """Verify email and password."""
    normalized_email = email.strip().lower()
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return None, "Invalid email or password."

    if not user.password_hash:
        return None, "This account was created with Google Sign-In. Please sign in with Google."

    if not verify_password(password, user.password_hash):
        return None, "Invalid email or password."

    if not user.is_active:
        return None, "This account is inactive. Please contact support."

    user.last_login_at = datetime.now(timezone.utc)
    await log_audit_event(
        db=db,
        user_id=user.id,
        event_type="USER_SIGNED_IN",
        metadata={"method": "email_password"}
    )
    await db.commit()
    await db.refresh(user)
    return user, None


async def handle_oauth_user(
    db: AsyncSession,
    provider: str,
    provider_account_id: str,
    email: str,
    full_name: str,
    avatar_url: Optional[str] = None,
) -> User:
    """Handle Google OAuth login: find existing, link account, or register new user."""
    normalized_email = email.strip().lower()

    # 1. Check if OAuthAccount exists
    stmt = select(OAuthAccount).where(
        OAuthAccount.provider == provider,
        OAuthAccount.provider_account_id == provider_account_id
    )
    result = await db.execute(stmt)
    oauth_acc = result.scalar_one_or_none()

    if oauth_acc:
        user_stmt = select(User).where(User.id == oauth_acc.user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one()
        user.last_login_at = datetime.now(timezone.utc)
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        await log_audit_event(
            db=db,
            user_id=user.id,
            event_type="GOOGLE_SIGN_IN",
            metadata={"existing_oauth": True}
        )
        await db.commit()
        await db.refresh(user)
        return user

    # 2. Check if user with same email exists
    stmt_email = select(User).where(User.email == normalized_email)
    res_email = await db.execute(stmt_email)
    user = res_email.scalar_one_or_none()

    if user:
        # Link OAuthAccount to existing user
        new_oauth = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_account_id=provider_account_id,
        )
        db.add(new_oauth)
        user.is_verified = True
        user.last_login_at = datetime.now(timezone.utc)
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        await log_audit_event(
            db=db,
            user_id=user.id,
            event_type="GOOGLE_SIGN_IN",
            metadata={"linked_existing_user": True}
        )
        await db.commit()
        await db.refresh(user)
        return user

    # 3. Create new User + OAuthAccount
    new_user = User(
        email=normalized_email,
        full_name=full_name or normalized_email.split("@")[0],
        avatar_url=avatar_url,
        is_active=True,
        is_verified=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    await db.flush()

    new_oauth = OAuthAccount(
        user_id=new_user.id,
        provider=provider,
        provider_account_id=provider_account_id,
    )
    db.add(new_oauth)
    await log_audit_event(
        db=db,
        user_id=new_user.id,
        event_type="USER_SIGNED_UP",
        metadata={"method": "google_oauth"}
    )
    await log_audit_event(
        db=db,
        user_id=new_user.id,
        event_type="GOOGLE_SIGN_IN",
        metadata={"first_time_oauth": True}
    )
    await db.commit()
    await db.refresh(new_user)
    return new_user
