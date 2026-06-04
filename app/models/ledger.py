import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EntryDirection(str, enum.Enum):
    DEBIT = "DEBIT"    # money leaving the wallet
    CREDIT = "CREDIT"  # money entering the wallet


class LedgerEntry(Base):
    """Immutable, append-only ledger. The source of truth for balances.
    Every money movement writes balanced entries (a CREDIT to one wallet has a
    matching DEBIT elsewhere, linked by `ref_type` + `ref_id`)."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[EntryDirection] = mapped_column(Enum(EntryDirection), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)

    ref_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "payment_link", "conversion", "topup"
    ref_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    wallet: Mapped["Wallet"] = relationship(back_populates="entries")  # noqa: F821
