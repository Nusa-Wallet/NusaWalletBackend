import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentLinkStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # held by the fraud engine for manual review


class PaymentLink(Base):
    """A payment request a merchant/freelancer issues in a target currency.
    The international payer opens the link in a browser — no app download needed
    (proposal section 11)."""

    __tablename__ = "payment_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    merchant_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    payer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[PaymentLinkStatus] = mapped_column(
        Enum(PaymentLinkStatus), default=PaymentLinkStatus.PENDING
    )
    # Fraud result stored with the transaction (Phase 13 integration).
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
