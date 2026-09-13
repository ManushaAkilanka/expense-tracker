from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="General", max_length=50)
    currency: str = Field(default="LKR", max_length=10)

    @field_validator("amount")
    @classmethod
    def validate_positive_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return round(v, 2)


class ExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=50)

    @field_validator("amount")
    @classmethod
    def validate_positive_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Amount must be greater than zero.")
            return round(v, 2)
        return v


class ExpenseResponse(BaseModel):
    id: str
    user_id: str
    amount: Decimal
    currency: str
    description: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseWithRunningBalance(ExpenseResponse):
    sequence_number: int
    running_balance: Decimal
    formatted_amount: str
    formatted_running_balance: str
    tx_code: str


class DashboardStats(BaseModel):
    total_spent: Decimal
    formatted_total_spent: str
    transaction_count: int
    currency: str = "LKR"
    session_id: str
    memory_state: str = "Persistent"
    data_structure: str = "list[float]"
    recent_expenses: List[ExpenseWithRunningBalance] = []
