"""Double-entry ledger helpers. Balances are always computed from entries,
never stored, so the books can't silently drift."""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EntryDirection, LedgerEntry, Wallet


def get_or_create_wallet(db: Session, user_id: int, currency: str) -> Wallet:
    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == user_id, Wallet.currency == currency)
        .first()
    )
    if wallet is None:
        wallet = Wallet(user_id=user_id, currency=currency)
        db.add(wallet)
        db.flush()
    return wallet


def get_balance(db: Session, wallet_id: int) -> Decimal:
    credits = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
        .filter(LedgerEntry.wallet_id == wallet_id, LedgerEntry.direction == EntryDirection.CREDIT)
        .scalar()
    )
    debits = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
        .filter(LedgerEntry.wallet_id == wallet_id, LedgerEntry.direction == EntryDirection.DEBIT)
        .scalar()
    )
    return Decimal(credits) - Decimal(debits)


def post_entry(
    db: Session,
    wallet: Wallet,
    direction: EntryDirection,
    amount: Decimal,
    ref_type: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        wallet_id=wallet.id,
        currency=wallet.currency,
        direction=direction,
        amount=amount,
        ref_type=ref_type,
        ref_id=ref_id,
        description=description,
    )
    db.add(entry)
    return entry


def transfer_same_currency(
    db: Session,
    from_wallet: Wallet,
    to_wallet: Wallet,
    amount: Decimal,
    ref_type: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> None:
    """A balanced movement: DEBIT one wallet, CREDIT another, same currency."""
    if from_wallet.currency != to_wallet.currency:
        raise ValueError("transfer_same_currency requires matching currencies")
    post_entry(db, from_wallet, EntryDirection.DEBIT, amount, ref_type, ref_id, description)
    post_entry(db, to_wallet, EntryDirection.CREDIT, amount, ref_type, ref_id, description)
