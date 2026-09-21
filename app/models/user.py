"""User ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(180), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Denormalized active role/center for backward-compatible route checks;
    # authority source of truth is CenterMembership (+ session active center).
    role: Mapped[str] = mapped_column(String(32), default=UserRole.SURGEON.value, index=True)
    institution_id: Mapped[str] = mapped_column(
        String(32),
        default=DEFAULT_INSTITUTION_CODE,
        index=True,
    )
    specialty: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    training_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    professional_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    account_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    surgeries: Mapped[list["Surgery"]] = relationship(  # noqa: F821
        back_populates="surgeon",
        foreign_keys="Surgery.surgeon_id",
    )
    memberships: Mapped[list["CenterMembership"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"
