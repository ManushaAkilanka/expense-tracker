import json
from decimal import Decimal
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


async def log_audit_event(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    amount: Optional[Decimal] = None,
    expense_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Record an immutable audit event for security and financial audit trails."""
    event = AuditEvent(
        user_id=user_id,
        expense_id=expense_id,
        event_type=event_type,
        amount=amount,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(event)
    await db.flush()
    return event
