"""Multi-center tenancy: centers, branding, memberships, supervisor links."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Center(Base):
    __tablename__ = "centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    short_name: Mapped[str] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    branding: Mapped[Optional["CenterBranding"]] = relationship(
        back_populates="center",
        uselist=False,
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["CenterMembership"]] = relationship(
        back_populates="center",
        cascade="all, delete-orphan",
    )


class CenterBranding(Base):
    __tablename__ = "center_branding"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id", ondelete="CASCADE"), unique=True)
    short_name: Mapped[str] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(255))
    logo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    logo_dark_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(16), default="#0b5ea8")
    secondary_color: Mapped[str] = mapped_column(String(16), default="#084a86")
    accent_color: Mapped[str] = mapped_column(String(16), default="#c9a227")
    text_color: Mapped[str] = mapped_column(String(16), default="#1a1a1a")
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    show_powered_by: Mapped[bool] = mapped_column(Boolean, default=True)
    report_header_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    placeholder_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    center: Mapped["Center"] = relationship(back_populates="branding")


class CenterMembership(Base):
    """Role assignment of a user within a center (source of truth for authorization)."""

    __tablename__ = "center_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "center_id", name="uq_membership_user_center"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
    center: Mapped["Center"] = relationship(back_populates="memberships")


class SupervisorAssignment(Base):
    """Supervisor may view assigned surgeons within the same center."""

    __tablename__ = "supervisor_assignments"
    __table_args__ = (
        UniqueConstraint(
            "center_id",
            "supervisor_user_id",
            "surgeon_user_id",
            name="uq_supervisor_surgeon",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id", ondelete="CASCADE"), index=True)
    supervisor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    surgeon_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    specialty: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    training_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    professional_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    privacy_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    center: Mapped["Center"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    center_id: Mapped[Optional[int]] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    before_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class RiskModelRun(Base):
    """Versioned surgical-risk model run metadata."""

    __tablename__ = "risk_model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[Optional[int]] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    version: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32), default="center")  # global|center|surgeon
    surgeon_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    n_cases: Mapped[int] = mapped_column(Integer, default=0)
    n_events: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_preliminary: Mapped[bool] = mapped_column(Boolean, default=True)
