"""Longitudinal refractive follow-up visits. No patient PII."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.constants import DEFAULT_INSTITUTION_CODE


class FollowUp(Base):
    """Post-operative refractive visit linked to an anonymous surgery case."""

    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    surgery_id: Mapped[int] = mapped_column(
        ForeignKey("surgeries.id", ondelete="CASCADE"),
        index=True,
    )
    institution_id: Mapped[str] = mapped_column(
        String(32),
        default=DEFAULT_INSTITUTION_CODE,
        index=True,
    )
    center_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("centers.id"),
        nullable=True,
        index=True,
    )
    visit_date: Mapped[date] = mapped_column(Date, index=True)
    visit_type: Mapped[str] = mapped_column(String(32), index=True)
    postoperative_days: Mapped[int] = mapped_column(Integer)

    udva_snellen: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    udva_logmar: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cdva_snellen: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    cdva_logmar: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    sphere: Mapped[float] = mapped_column(Float)
    cylinder: Mapped[float] = mapped_column(Float)
    axis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    spherical_equivalent: Mapped[float] = mapped_column(Float)
    residual_astigmatism: Mapped[float] = mapped_column(Float)
    astigmatism_orientation: Mapped[str] = mapped_column(String(16))

    spherical_equivalent_stars: Mapped[int] = mapped_column(Integer)
    astigmatism_stars: Mapped[int] = mapped_column(Integer)
    # Mean of SEQ★ and Ast★ (float). Legacy INTEGER affinity still accepts floats in SQLite.
    overall_refractive_stars: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
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

    surgery: Mapped["Surgery"] = relationship(  # noqa: F821
        back_populates="follow_ups",
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821
    revisions: Mapped[list["FollowUpRevision"]] = relationship(
        back_populates="follow_up",
        cascade="all, delete-orphan",
        order_by="FollowUpRevision.created_at.desc()",
    )


class FollowUpRevision(Base):
    """Snapshot history when a follow-up is edited or voided."""

    __tablename__ = "follow_up_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    follow_up_id: Mapped[int] = mapped_column(
        ForeignKey("follow_ups.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32))  # created | updated | voided
    snapshot_json: Mapped[str] = mapped_column(Text)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    follow_up: Mapped["FollowUp"] = relationship(back_populates="revisions")
    changed_by: Mapped["User"] = relationship(foreign_keys=[changed_by_id])  # noqa: F821
