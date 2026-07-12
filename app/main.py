"""PhacoStats FastAPI application entrypoint."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.deps import NotAuthenticatedError
from app.routers import (
    admin_analytics,
    auth,
    dashboard,
    followups,
    profile,
    refractive,
    reinterventions,
    surgeries,
    users,
)
# Import models so metadata includes FollowUp tables
from app import models as _models  # noqa: F401
from app.seed import seed_if_empty

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent


def _ensure_schema() -> None:
    """Create tables; migrate additive columns; rebuild when legacy PCR schema is detected."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    legacy = "pcr_events" in tables
    missing_new = "users" in tables and "complication_events" not in tables
    if legacy or missing_new:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Additive SQLite migrations for existing demo DBs
    inspector = inspect(engine)
    if "surgeries" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("surgeries")}
        with engine.begin() as conn:
            if "reintervention_needed" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE surgeries "
                        "ADD COLUMN reintervention_needed BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            if "reintervention_procedure_notes" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE surgeries "
                        "ADD COLUMN reintervention_procedure_notes TEXT"
                    )
                )
            if "iol_type" not in columns:
                conn.execute(text("ALTER TABLE surgeries ADD COLUMN iol_type VARCHAR(32)"))
            if "institution_id" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE surgeries "
                        "ADD COLUMN institution_id VARCHAR(32) NOT NULL DEFAULT 'CODET'"
                    )
                )
    if "users" in inspector.get_table_names():
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "institution_id" not in user_cols:
                conn.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN institution_id VARCHAR(32) NOT NULL DEFAULT 'CODET'"
                    )
                )

    # Migrate legacy bool reintervention → follow-up rows (idempotent)
    try:
        from app.services.reinterventions import migrate_legacy_reinterventions

        db = SessionLocal()
        try:
            migrate_legacy_reinterventions(db)
        finally:
            db.close()
    except Exception:
        # Tables may not be ready in edge cases; create_all already ran.
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_schema()
    if os.getenv("PHACOSTATS_TESTING") != "1":
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(refractive.router)
app.include_router(admin_analytics.router)
app.include_router(followups.router)
app.include_router(surgeries.router)
app.include_router(reinterventions.router)
app.include_router(users.router)
app.include_router(profile.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(_: Request, __: NotAuthenticatedError):
    return RedirectResponse("/login", status_code=303)
