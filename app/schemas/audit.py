from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    id: str
    user_id: str
    expense_id: Optional[str] = None
    event_type: str
    amount: Optional[Decimal] = None
    metadata_json: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
