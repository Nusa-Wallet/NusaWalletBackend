"""Double-entry ledger helpers. Balances are always computed from entries,
never stored, so the books can't silently drift."""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EntryDirection, LedgerEntry, User, Wallet


SYSTEM_ACCOUNT_EMAILS = {
    "cash_clearing": "system+cash-clearing@nusawallet.internal",
    "fx_inventory": "system+fx-inventory@nusawallet.internal",
    "platform_fee": "system+platform-fee@nusawallet.internal",
}


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


def get_system_user(db: Session, account: str) -> User:
    """Return the synthetic owner for a system ledger account."""
    email = SYSTEM_ACCOUNT_EMAILS[account]
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            full_name=f"NusaWallet {account.replace('_', ' ').title()}",
            hashed_password="system-account-no-login",
            is_verified=True,
        )
        db.add(user)
        db.flush()
    return user


def get_system_wallet(db: Session, account: str, currency: str) -> Wallet:
    user = get_system_user(db, account)
    return get_or_create_wallet(db, user.id, currency.upper())


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


def record_external_credit(
    db: Session,
    to_wallet: Wallet,
    amount: Decimal,
    ref_type: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> None:
    """Balance an incoming external payment/top-up against the cash-clearing account."""
    clearing = get_system_wallet(db, "cash_clearing", to_wallet.currency)
    post_entry(db, clearing, EntryDirection.DEBIT, amount, ref_type, ref_id, description)
    post_entry(db, to_wallet, EntryDirection.CREDIT, amount, ref_type, ref_id, description)


def record_fx_conversion(
    db: Session,
    from_wallet: Wallet,
    to_wallet: Wallet,
    amount_in: Decimal,
    gross_out: Decimal,
    fee: Decimal,
    ref_id: str | None = None,
    description: str | None = None,
) -> None:
    """Record a cross-currency conversion with balanced entries per currency.

    Source currency: user debit is balanced by FX inventory credit.
    Destination currency: FX inventory debit is balanced by user net credit plus
    platform fee credit.
    """
    fx_src = get_system_wallet(db, "fx_inventory", from_wallet.currency)
    fx_dst = get_system_wallet(db, "fx_inventory", to_wallet.currency)
    fee_wallet = get_system_wallet(db, "platform_fee", to_wallet.currency)

    post_entry(db, from_wallet, EntryDirection.DEBIT, amount_in, "conversion", ref_id, description)
    post_entry(db, fx_src, EntryDirection.CREDIT, amount_in, "conversion", ref_id, description)
    post_entry(db, fx_dst, EntryDirection.DEBIT, gross_out, "conversion", ref_id, description)
    post_entry(
        db,
        to_wallet,
        EntryDirection.CREDIT,
        gross_out - fee,
        "conversion",
        ref_id,
        description,
    )
    if fee > 0:
        post_entry(db, fee_wallet, EntryDirection.CREDIT, fee, "conversion_fee", ref_id, description)
