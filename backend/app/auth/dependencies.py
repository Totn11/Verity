from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import read_session
from app.auth.tokens import TokenConfigurationError
from app.db.models import User
from app.db.session import get_session

# Authorization matrix:
# - People, rooms, attendance, and reports reads: admin or staff.
# - Attendance check-in/check-out: admin or staff.
# - People and rooms writes: admin only.
# - All /api/roles endpoints, audit-log viewing, and user management: admin only.


async def require_user(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> User:
    """Require a valid, active database-backed session."""
    try:
        user = await read_session(request, db)
    except TokenConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    return user


def require_role(*roles: str) -> Callable[..., Any]:
    """Require the authenticated user to have one of the supplied roles."""
    accepted_roles = frozenset(roles)

    async def enforce_role(user: User = Depends(require_user)) -> User:
        role = getattr(user.role, "value", user.role)
        if role not in accepted_roles:
            raise HTTPException(status_code=403, detail="You do not have permission.")
        return user

    return enforce_role
