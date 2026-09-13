import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    expense_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("expenses.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False
    )
    amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="audit_events")

    __table_args__ = (
        Index("ix_audit_events_user_created", "user_id", "created_at"),
    )
