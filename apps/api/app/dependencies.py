import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
