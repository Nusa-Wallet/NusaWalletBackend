from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models import EntryDirection, User
from app.schemas.wallet import ConvertRequest
from app.services import fx, ledger

router = APIRouter(prefix="/settlement", tags=["settlement"])

# Small platform fee on successful conversion (proposal: 0.5%-1.0%).
CONVERSION_FEE_RATE = Decimal("0.005")


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

    src = ledger.get_or_create_wallet(db, current.id, src_ccy)
    dst = ledger.get_or_create_wallet(db, current.id, dst_ccy)
    db.flush()

    if ledger.get_balance(db, src.id) < payload.amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient balance")

    rate = fx.get_rate(src_ccy, dst_ccy)
    gross = payload.amount * rate
    fee = (gross * CONVERSION_FEE_RATE).quantize(Decimal("0.0001"))
    net = gross - fee

    ref = f"conv-{src_ccy}-{dst_ccy}"
    ledger.post_entry(db, src, EntryDirection.DEBIT, payload.amount, "conversion", ref,
                      f"Convert to {dst_ccy} @ {rate}")
    ledger.post_entry(db, dst, EntryDirection.CREDIT, net, "conversion", ref,
                      f"Converted from {src_ccy} (fee {fee})")
    db.commit()

    return {
        "from_currency": src_ccy,
        "to_currency": dst_ccy,
        "amount_in": payload.amount,
        "rate": rate,
        "fee": fee,
        "amount_out": net,
    }
