from decimal import Decimal

from pydantic import BaseModel, Field


class WalletBalance(BaseModel):
    currency: str
    balance: Decimal


class LedgerEntryResponse(BaseModel):
    id: int
    currency: str
    direction: str
    amount: Decimal
    ref_type: str
    description: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ConvertRequest(BaseModel):
    from_currency: str
    to_currency: str
    amount: Decimal
    # Portion to convert now, from the AI split recommendation (Phase 13). 100 = all now.
    convert_percentage: int = Field(default=100, ge=1, le=100)
    idempotency_key: str | None = Field(default=None, max_length=128)
