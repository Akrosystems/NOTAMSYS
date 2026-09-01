import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.security import decode_token
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
_service_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)
) -> User:
    try:
        subject = decode_token(token)
        user = await session.get(User, uuid.UUID(subject))
    except (jwt.InvalidTokenError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Throttled update of last_seen_at (at most once every 30 seconds per session).
    # Normalizes timezone across PostgreSQL (aware) and SQLite (naive) safely.
    now = datetime.now(UTC)
    last_seen = user.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    if last_seen is None or (now - last_seen).total_seconds() > 30:
        user.last_seen_at = now
        await session.commit()

    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        # SYSTEM_ADMIN is a superset of every other role -- one bypass here
        # instead of listing it in every require_roles(...) call at every
        # call site. Business-logic checks that aren't role-based (e.g. the
        # four-eyes self-approval guard) still apply to admins.
        if user.role != Role.SYSTEM_ADMIN and user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role for this operation")
        return user

    return dependency


async def require_service_key(key: str | None = Security(_service_key_header)) -> None:
    """Machine-to-machine auth for app/aftn_bridge.py -- ATSEP's on-prem
    poller has no user account and shouldn't get one; it's not a person
    logging in. Deliberately separate from get_current_user/JWT so a leaked
    bridge key can be rotated without touching any human's session, and a
    leaked human session can never reach these endpoints."""
    if not settings.aftn_bridge_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AFTN bridge is not configured (NOTAMSYS_AFTN_BRIDGE_API_KEY unset)",
        )
    if key != settings.aftn_bridge_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
