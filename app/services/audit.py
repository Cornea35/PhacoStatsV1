"""Audit log helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    actor_user_id: int | None = None,
    center_id: int | None = None,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        center_id=center_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        before_json=None if before is None else json.dumps(before, default=str),
        after_json=None if after is None else json.dumps(after, default=str),
    )
    db.add(entry)
    db.flush()
    return entry
