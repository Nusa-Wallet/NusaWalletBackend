import secrets
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import PaymentLink, PaymentLinkStatus, User
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


def _fraud_score(link: PaymentLink, payer_name: str, origin_country: str | None,
                 is_new_payer: bool) -> dict:
    """Best-effort call to the AI fraud service with full transaction context.

    Never blocks the demo if the AI service is down — returns an explicit benign
    fallback (LOW / ALLOW) so the payment flow can still proceed."""
    payload = {
        "transaction_id": link.code,
        "amount": float(link.amount),
        "currency": link.currency,
        "payer_name": payer_name,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "is_new_payer": is_new_payer,
    }
    if origin_country:
        payload["origin_country"] = origin_country.upper()
    try:
        resp = httpx.post(f"{settings.ai_service_url}/fraud/score", json=payload, timeout=3.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {
            "risk_score": 0.0, "risk_level": "LOW", "flagged": False,
            "recommended_action": "ALLOW", "factors": [], "reason": "ai-service-unavailable",
        }


def _transition_link(link: PaymentLink, target: PaymentLinkStatus) -> None:
    allowed = {
        PaymentLinkStatus.PENDING: {
            PaymentLinkStatus.PAID,
            PaymentLinkStatus.REVIEW_REQUIRED,
            PaymentLinkStatus.EXPIRED,
        },
        PaymentLinkStatus.PAID: set(),
        PaymentLinkStatus.REVIEW_REQUIRED: set(),
        PaymentLinkStatus.EXPIRED: set(),
    }
    if link.status == target:
        return
    if target not in allowed[link.status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition payment link from {link.status.value} to {target.value}",
        )
    link.status = target


def _paid_response(link: PaymentLink) -> dict:
    return {
        "status": "PAID",
        "credited": link.amount,
        "currency": link.currency,
        "risk_score": link.risk_score,
        "risk_level": link.risk_level,
        "idempotent": True,
    }


def _review_required_error(link: PaymentLink, factors: list[str] | None = None) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "status": "REVIEW_REQUIRED",
            "risk_score": link.risk_score,
            "risk_level": link.risk_level,
            "factors": factors or [],
            "idempotent": True,
        },
    )


@router.post("/{code}/pay")
def pay_link(code: str, payload: PayLinkRequest, db: Session = Depends(get_db)):
    """Simulate an international payer paying the link. On success, the merchant's
    foreign-currency wallet is CREDITED (proposal step 2-3)."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    if link.status == PaymentLinkStatus.PAID:
        return _paid_response(link)
    if link.status == PaymentLinkStatus.REVIEW_REQUIRED:
        raise _review_required_error(link)
    if link.status != PaymentLinkStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Link is {link.status.value}")

    # Has this merchant been paid by this payer before? (first-time payer is riskier)
    is_new_payer = (
        db.query(PaymentLink)
        .filter(
            PaymentLink.merchant_user_id == link.merchant_user_id,
            PaymentLink.payer_name == payload.payer_name,
            PaymentLink.status == PaymentLinkStatus.PAID,
        )
        .first()
        is None
    )

    fraud = _fraud_score(link, payload.payer_name, payload.origin_country, is_new_payer)
    link.risk_score = float(fraud.get("risk_score") or 0.0)
    link.risk_level = fraud.get("risk_level")
    link.payer_name = payload.payer_name

    # HIGH risk / REVIEW_REQUIRED holds the payment for manual review — not credited.
    needs_review = fraud.get("recommended_action") == "REVIEW_REQUIRED" or fraud.get("flagged")
    if needs_review:
        _transition_link(link, PaymentLinkStatus.REVIEW_REQUIRED)
        db.commit()
        raise _review_required_error(link, fraud.get("factors", []))

    wallet = ledger.get_or_create_wallet(db, link.merchant_user_id, link.currency)
    db.flush()
    ledger.record_external_credit(
        db, wallet, link.amount, "payment_link", link.code,
        f"Payment from {payload.payer_name}",
    )
    _transition_link(link, PaymentLinkStatus.PAID)
    link.paid_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "PAID", "credited": link.amount, "currency": link.currency,
        "risk_score": link.risk_score, "risk_level": link.risk_level, "fraud": fraud,
    }
