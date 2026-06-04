import secrets
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import EntryDirection, PaymentLink, PaymentLinkStatus, User
from app.schemas.payment_link import (
    CreatePaymentLinkRequest,
    PayLinkRequest,
    PaymentLinkResponse,
)
from app.services import ledger

router = APIRouter(prefix="/payment-links", tags=["payment-links"])


def _to_response(link: PaymentLink) -> PaymentLinkResponse:
    return PaymentLinkResponse(
        code=link.code,
        currency=link.currency,
        amount=link.amount,
        note=link.note,
        status=link.status.value,
        url=f"/payment-links/{link.code}",
    )


@router.post("", response_model=PaymentLinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: CreatePaymentLinkRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merchant issues a payment link in a target currency (Design 10/11)."""
    link = PaymentLink(
        code=secrets.token_urlsafe(8),
        merchant_user_id=current.id,
        currency=payload.currency.upper(),
        amount=payload.amount,
        note=payload.note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _to_response(link)


@router.get("/{code}", response_model=PaymentLinkResponse)
def get_link(code: str, db: Session = Depends(get_db)):
    """Public — payer opens this in a browser, no app/login needed."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    return _to_response(link)


def _fraud_score(amount: Decimal, currency: str, payer_name: str) -> dict:
    """Best-effort call to the separate AI service. Never blocks the demo if
    the service is down — returns a benign default."""
    try:
        resp = httpx.post(
            f"{settings.ai_service_url}/fraud/score",
            json={"amount": float(amount), "currency": currency, "payer_name": payer_name},
            timeout=3.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"risk_score": 0.0, "flagged": False, "reason": "ai-service-unavailable"}


@router.post("/{code}/pay")
def pay_link(code: str, payload: PayLinkRequest, db: Session = Depends(get_db)):
    """Simulate an international payer paying the link. On success, the merchant's
    foreign-currency wallet is CREDITED (proposal step 2-3)."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    if link.status != PaymentLinkStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Link is {link.status.value}")

    fraud = _fraud_score(link.amount, link.currency, payload.payer_name)
    if fraud.get("flagged"):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Transaction flagged for review (risk {fraud.get('risk_score')})",
        )

    wallet = ledger.get_or_create_wallet(db, link.merchant_user_id, link.currency)
    db.flush()
    ledger.post_entry(
        db, wallet, EntryDirection.CREDIT, link.amount, "payment_link", link.code,
        f"Payment from {payload.payer_name}",
    )
    link.status = PaymentLinkStatus.PAID
    link.payer_name = payload.payer_name
    link.paid_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "PAID", "credited": link.amount, "currency": link.currency, "fraud": fraud}
