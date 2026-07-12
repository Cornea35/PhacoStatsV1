"""Limited operational export for coordinator role."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session, joinedload

from app.constants import (
    REINTERVENTION_REQUIRED_LABELS,
    REINTERVENTION_STATUS_LABELS,
    REINTERVENTION_TYPE_LABELS,
)
from app.models import Surgery
from app.services.reinterventions import latest_active_for_surgery


OPS_HEADERS = [
    "Identificador",
    "Fecha cirugía",
    "Cirujano",
    "Ojo",
    "Tipo de cirugía",
    "Complicación",
    "Reintervención requerida",
    "Tipo general reintervención",
    "Fecha reintervención",
    "Estado",
    "Notas administrativas",
]


def export_ops_xlsx(db: Session, *, institution_id: str | None) -> bytes:
    q = (
        db.query(Surgery)
        .options(
            joinedload(Surgery.surgeon),
            joinedload(Surgery.complication),
            joinedload(Surgery.reintervention_follow_ups),
        )
        .order_by(Surgery.surgery_date.desc(), Surgery.id.desc())
    )
    if institution_id:
        q = q.filter(Surgery.institution_id == institution_id)
    rows = q.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Operativo"
    ws.append(OPS_HEADERS)
    for s in rows:
        active = latest_active_for_surgery(s)
        had_comp = bool(s.complication and s.complication.occurred)
        if active:
            req = REINTERVENTION_REQUIRED_LABELS.get(
                active.reintervention_required, active.reintervention_required
            )
            rtype = REINTERVENTION_TYPE_LABELS.get(
                active.reintervention_type, active.reintervention_type
            )
            rdate = active.reintervention_date.isoformat() if active.reintervention_date else ""
            status = REINTERVENTION_STATUS_LABELS.get(active.status, active.status)
            notes = active.notes or ""
        else:
            req = "Sí" if s.reintervention_needed else "No necesaria"
            rtype = ""
            rdate = ""
            status = "Pendiente" if s.reintervention_needed else "No necesaria"
            notes = s.reintervention_procedure_notes or ""
        ws.append(
            [
                s.case_code,
                s.surgery_date.isoformat(),
                s.surgeon.full_name if s.surgeon else "",
                s.eye,
                s.technique,
                "Sí" if had_comp else "No",
                req,
                rtype,
                rdate,
                status,
                notes,
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
