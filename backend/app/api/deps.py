"""FrigoCore — Auth dependencies: current user, role gate, object visibility."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_access_token
from app.database import get_db
from app.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nie zalogowano",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    payload = decode_access_token(token)
    if payload is None:
        raise unauthorized
    user = await db.get(User, payload["sub"], options=[selectinload(User.objects)])
    if user is None or not user.is_active:
        raise unauthorized
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wymagane uprawnienia administratora")
    return user


def get_visible_object_ids(user: User) -> Optional[set[UUID]]:
    """None means "every object" (admin/serwisant); a set scopes a `user` role account."""
    if user.role in (UserRole.ADMIN, UserRole.SERWISANT):
        return None
    return {obj.id for obj in user.objects}
