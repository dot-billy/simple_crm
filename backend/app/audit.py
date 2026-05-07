"""Audit log helpers for entity mutations.

The route handlers call these to record who changed what when. The functions
add to the session but never commit — the caller commits as part of its own
transaction so the audit row is consistent with the underlying mutation.
"""
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEventType, AuditLog, User


def _json_default(o: Any) -> Any:
    if isinstance(o, (UUID, datetime, date)):
        return str(o)
    if isinstance(o, Enum):
        return o.value
    return str(o)


def _serialize(obj: Any) -> dict | None:
    """Convert a SQLAlchemy model instance to a JSON-friendly dict."""
    if obj is None:
        return None
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    if isinstance(obj, dict):
        return obj
    return None


def _diff(before: dict | None, after: dict | None) -> dict:
    """Return only the keys that changed between before and after."""
    if before is None or after is None:
        return after or before or {}
    diff = {}
    keys = set(before.keys()) | set(after.keys())
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diff[k] = {"before": b, "after": a}
    return diff


def log_mutation(
    db: AsyncSession,
    *,
    event_type: AuditEventType,
    user: User | None,
    entity_type: str,
    entity_id: UUID | None,
    before: Any = None,
    after: Any = None,
    detail: str | None = None,
) -> AuditLog:
    """Add an audit row to the session. Caller commits."""
    before_dict = _serialize(before)
    after_dict = _serialize(after)
    if before_dict is not None and after_dict is not None:
        delta = _diff(before_dict, after_dict)
        before_state = json.dumps({k: v["before"] for k, v in delta.items()}, default=_json_default) if delta else None
        after_state = json.dumps({k: v["after"] for k, v in delta.items()}, default=_json_default) if delta else None
    else:
        before_state = json.dumps(before_dict, default=_json_default) if before_dict else None
        after_state = json.dumps(after_dict, default=_json_default) if after_dict else None

    row = AuditLog(
        event_type=event_type,
        user_id=user.id if user else None,
        email=user.email if user else None,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        detail=detail,
    )
    db.add(row)
    return row
