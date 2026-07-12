"""Administrative reintervention follow-up (ops tracking, not clinical metrics)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReinterventionFollowUp(Base):
    """Coordinator/admin reintervention tracking linked to an anonymous surgery."""

    __tablename__ = "reintervention_follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    surgery_id: Mapped[int] = mapped_column(
        ForeignKey("surgeries.id", ondelete="CASCADE"),
        index=True,
    )
    reintervention_required: Mapped[str] = mapped_column(String(16), index=True)
    reintervention_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    reintervention_type: Mapped[str] = mapped_column(String(64), default="unspecified")
    retina_related: Mapped[str] = mapped_column(String(16), default="unknown")
    status: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    is_voided: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    surgery: Mapped["Surgery"] = relationship(  # noqa: F821
        back_populates="reintervention_follow_ups",
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_user_id])  # noqa: F821
    updated_by: Mapped[Optional["User"]] = relationship(foreign_keys=[updated_by_user_id])  # noqa: F821
    voided_by: Mapped[Optional["User"]] = relationship(foreign_keys=[voided_by_user_id])  # noqa: F821
    revisions: Mapped[list["ReinterventionRevision"]] = relationship(
        back_populates="follow_up",
        cascade="all, delete-orphan",
        order_by="ReinterventionRevision.created_at.desc()",
    )


class ReinterventionRevision(Base):
    """Audit snapshot for reintervention create/update/void."""

    __tablename__ = "reintervention_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    follow_up_id: Mapped[int] = mapped_column(
        ForeignKey("reintervention_follow_ups.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32))  # created | updated | voided
    previous_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_json: Mapped[str] = mapped_column(Text)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    follow_up: Mapped["ReinterventionFollowUp"] = relationship(back_populates="revisions")
    changed_by: Mapped["User"] = relationship(foreign_keys=[changed_by_id])  # noqa: F821
