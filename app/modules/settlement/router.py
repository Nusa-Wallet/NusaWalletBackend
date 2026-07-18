from decimal import Decimal
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import Conversion, ConversionStatus, User
from app.schemas.wallet import ConvertRequest
from app.services.ai_audit import record_ai_audit
from app.services import fx, ledger

router = APIRouter(prefix="/settlement", tags=["settlement"])

# Small platform fee on successful conversion (proposal: 0.5%-1.0%).
CONVERSION_FEE_RATE = Decimal("0.005")


def _transition_conversion(conversion: Conversion, target: ConversionStatus) -> None:
    allowed = {
        ConversionStatus.PENDING: {ConversionStatus.COMPLETED, ConversionStatus.FAILED},
        ConversionStatus.COMPLETED: set(),
        ConversionStatus.FAILED: set(),
    }
    if conversion.status == target:
        return
    if target not in allowed[conversion.status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition conversion from {conversion.status.value} to {target.value}",
        )
    conversion.status = target


def _conversion_response(conversion: Conversion, *, idempotent: bool = False) -> dict:
    return {
        "transaction_id": conversion.id,
        "status": conversion.status.value,
        "idempotent": idempotent,
        "from_currency": conversion.from_currency,
        "to_currency": conversion.to_currency,
        "convert_percentage": conversion.convert_percentage,
        "amount_requested": conversion.amount_requested,
        "amount_in": conversion.amount_in,
        "amount_held": conversion.amount_held,
        "rate": conversion.rate,
        "fee": conversion.fee,
        "amount_out": conversion.amount_out,
    }


def _fx_advisory_snapshot(src_ccy: str, dst_ccy: str, amount: Decimal) -> tuple[dict, dict, str, str | None]:
    request_payload = {
        "base": src_ccy,
        "quote": dst_ccy,
        "amount": float(amount),
        "horizon_days": 7,
        "risk_preference": "MODERATE",
    }
    try:
        resp = httpx.get(
            f"{settings.ai_service_url}/fx/advisory",
            params=request_payload,
            timeout=3.0,
        )
        resp.raise_for_status()
        return request_payload, resp.json(), "SUCCESS", None
    except Exception as exc:
        return request_payload, {
            "pair": f"{src_ccy}/{dst_ccy}",
            "model_version": "unavailable",
            "reason": "ai-service-unavailable",
        }, "FALLBACK", str(exc)


@router.post("/convert")
def convert(
    payload: ConvertRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Convert balance from one currency to another (Design 08 'Konversi').
    DEBIT the source wallet, CREDIT the destination at the spot rate, minus fee."""
    src_ccy = payload.from_currency.upper()
    dst_ccy = payload.to_currency.upper()
    if src_ccy == dst_ccy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Currencies must differ")

    if payload.idempotency_key:
        existing = (
            db.query(Conversion)
            .filter(
                Conversion.user_id == current.id,
                Conversion.idempotency_key == payload.idempotency_key,
            )
            .first()
        )
        if existing:
            if existing.status == ConversionStatus.COMPLETED:
                return _conversion_response(existing, idempotent=True)
            if existing.status == ConversionStatus.FAILED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "status": existing.status.value,
                        "transaction_id": existing.id,
                        "failure_reason": existing.failure_reason,
                        "idempotent": True,
                    },
                )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "status": existing.status.value,
                    "transaction_id": existing.id,
                    "idempotent": True,
                },
            )

    conversion = Conversion(
        user_id=current.id,
        idempotency_key=payload.idempotency_key,
        from_currency=src_ccy,
        to_currency=dst_ccy,
        amount_requested=payload.amount,
        convert_percentage=payload.convert_percentage,
    )
    db.add(conversion)
    db.flush()

    src = ledger.get_or_create_wallet(db, current.id, src_ccy)
    dst = ledger.get_or_create_wallet(db, current.id, dst_ccy)
    db.flush()

    # Convert only the recommended portion now (AI split recommendation); rest is held.
    pct = Decimal(payload.convert_percentage) / Decimal(100)
    convert_amount = (payload.amount * pct).quantize(Decimal("0.0001"))

    if ledger.get_balance(db, src.id) < convert_amount:
        conversion.failure_reason = "Insufficient balance"
        _transition_conversion(conversion, ConversionStatus.FAILED)
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "status": conversion.status.value,
                "transaction_id": conversion.id,
                "failure_reason": conversion.failure_reason,
            },
        )

    rate = fx.get_rate(src_ccy, dst_ccy)
    gross = convert_amount * rate
    fee = (gross * CONVERSION_FEE_RATE).quantize(Decimal("0.0001"))
    net = gross - fee

    ref = f"conv-{conversion.id}"
    advisory_request, advisory_response, audit_status, audit_error = _fx_advisory_snapshot(
        src_ccy,
        dst_ccy,
        convert_amount,
    )
    record_ai_audit(
        db,
        ref_type="conversion",
        ref_id=ref,
        purpose="fx_advisory",
        status=audit_status,
        request_payload=advisory_request,
        response_payload=advisory_response,
        error=audit_error,
    )
    ledger.record_fx_conversion(
        db,
        src,
        dst,
        convert_amount,
        gross,
        fee,
        ref,
        f"Convert {src_ccy} to {dst_ccy} @ {rate}",
    )
    conversion.amount_in = convert_amount
    conversion.amount_held = (payload.amount - convert_amount).quantize(Decimal("0.0001"))
    conversion.rate = rate
    conversion.fee = fee
    conversion.amount_out = net
    conversion.completed_at = datetime.now(timezone.utc)
    _transition_conversion(conversion, ConversionStatus.COMPLETED)
    db.commit()
    db.refresh(conversion)

    return _conversion_response(conversion)
