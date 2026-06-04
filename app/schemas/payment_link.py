from decimal import Decimal

from pydantic import BaseModel


class CreatePaymentLinkRequest(BaseModel):
    currency: str
    amount: Decimal
    note: str | None = None


class PaymentLinkResponse(BaseModel):
    code: str
    currency: str
    amount: Decimal
    note: str | None
    status: str
    url: str


class PayLinkRequest(BaseModel):
    payer_name: str
