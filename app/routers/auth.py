"""Auth routes: login / logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import flash, get_current_user_optional, pop_flashes
from app.models import User
from app.security import create_session_token, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: Annotated[User | None, Depends(get_current_user_optional)]):
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"flashes": pop_flashes(request)},
    )


@router.post("/login")
def login_submit(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        flash(request, "Usuario o contraseña incorrectos.", "danger")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    token = create_session_token(user.id)
    redirect = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )
    flash(request, f"Bienvenido/a, {user.full_name}.", "success")
    return redirect


@router.post("/logout")
def logout(request: Request):
    redirect = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(settings.session_cookie_name)
    flash(request, "Sesión cerrada.", "info")
    return redirect
