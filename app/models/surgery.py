"""Surgery, risk factors, and complication ORM models.

IMPORTANT: Never store real patient identifiers. Use anonymous case codes only.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import DEFAULT_INSTITUTION_CODE
from app.database import Base


class Surgery(Base):
    __tablename__ = "surgeries"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    surgery_date: Mapped[date] = mapped_column(Date, index=True)
    eye: Mapped[str] = mapped_column(String(2))
    technique: Mapped[str] = mapped_column(String(80), default="Phacoemulsification")
    iol_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    institution_id: Mapped[str] = mapped_column(
        String(32),
        default=DEFAULT_INSTITUTION_CODE,
        index=True,
    )
    center_id: Mapped[Optional[int]] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Post-operative follow-up (admin-managed)
    reintervention_needed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reintervention_procedure_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    surgeon_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    surgeon: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[surgeon_id],
        back_populates="surgeries",
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821
    risk_factors: Mapped[list["RiskFactor"]] = relationship(
        back_populates="surgery",
        cascade="all, delete-orphan",
    )
    complication: Mapped[Optional["ComplicationEvent"]] = relationship(
        back_populates="surgery",
        uselist=False,
        cascade="all, delete-orphan",
    )
    follow_ups: Mapped[list["FollowUp"]] = relationship(  # noqa: F821
        back_populates="surgery",
        cascade="all, delete-orphan",
        order_by="FollowUp.visit_date.desc()",
    )
    reintervention_follow_ups: Mapped[list["ReinterventionFollowUp"]] = relationship(  # noqa: F821
        back_populates="surgery",
        cascade="all, delete-orphan",
        order_by="ReinterventionFollowUp.created_at.desc()",
    )


class RiskFactor(Base):
    __tablename__ = "risk_factors"
    __table_args__ = (UniqueConstraint("surgery_id", "code", name="uq_surgery_risk_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    surgery_id: Mapped[int] = mapped_column(ForeignKey("surgeries.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))

    surgery: Mapped["Surgery"] = relationship(back_populates="risk_factors")


class ComplicationEvent(Base):
    """Intraoperative complication details for a surgery."""

    __tablename__ = "complication_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    surgery_id: Mapped[int] = mapped_column(
        ForeignKey("surgeries.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    occurred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    complication_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    surgical_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vitreous_loss: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    anterior_vitrectomy: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fragments_to_posterior: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    retina_intervention: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    iol_position: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    capsular_tension_ring: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    segment_ring_suture: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    f2_assistant_help: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    surgery: Mapped["Surgery"] = relationship(back_populates="complication")
