from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import LedgerEntry, User, Wallet
from app.schemas.wallet import LedgerEntryResponse, WalletBalance
from app.services import ledger
from app.services.fx import get_rate

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get("/rates")
def get_rates():
    """Public — current spot rates vs IDR for all supported currencies."""
    result: dict[str, float] = {"IDR": 1.0}
    for ccy in ["USD", "SGD", "EUR", "MYR"]:
        result[ccy] = float(get_rate(ccy, "IDR"))
    return result


@router.get("", response_model=list[WalletBalance])
def list_wallets(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    balances: list[WalletBalance] = []
    for currency in settings.supported_currencies:
        wallet = ledger.get_or_create_wallet(db, current.id, currency)
        db.commit()
        balances.append(
            WalletBalance(currency=currency, balance=ledger.get_balance(db, wallet.id))
        )
    return balances


@router.get("/transactions/recent", response_model=list[LedgerEntryResponse])
def recent_transactions(
    limit: int = 10,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent entries across ALL wallets — used by the home screen transaction list."""
    wallet_ids = [w.id for w in db.query(Wallet).filter(Wallet.user_id == current.id).all()]
    if not wallet_ids:
        return []
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.wallet_id.in_(wallet_ids))
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        LedgerEntryResponse(
            id=e.id,
            currency=e.currency,
            direction=e.direction.value,
            amount=e.amount,
            ref_type=e.ref_type,
            description=e.description,
            created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]


@router.get("/{currency}/history", response_model=list[LedgerEntryResponse])
def wallet_history(
    currency: str,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == current.id, Wallet.currency == currency.upper())
        .first()
    )
    if wallet is None:
        return []
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.wallet_id == wallet.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        LedgerEntryResponse(
            id=e.id,
            currency=e.currency,
            direction=e.direction.value,
            amount=e.amount,
            ref_type=e.ref_type,
            description=e.description,
            created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]
