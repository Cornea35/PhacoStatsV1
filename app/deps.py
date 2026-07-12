"""FastAPI dependencies: DB session, current user, role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import UserRole
from app.database import get_db
from app.models import User
from app.security import decode_session_token

settings = get_settings()


class NotAuthenticatedError(Exception):
    """Raised when a protected route is accessed without a valid session."""


def get_current_user_optional(
    db: Annotated[Session, Depends(get_db)],
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> User | None:
    if not session:
        return None
    user_id = decode_session_token(session)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise NotAuthenticatedError()
    return user


def require_roles(*roles: UserRole) -> Callable:
    allowed = {r.value for r in roles}

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción.",
            )
        return user

    return dependency


def flash(request: Request, message: str, category: str = "success") -> None:
    messages = request.session.setdefault("_flash", [])
    messages.append({"message": message, "category": category})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flash", [])
