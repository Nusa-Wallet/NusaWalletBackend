from decimal import Decimal

from pydantic import BaseModel


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
