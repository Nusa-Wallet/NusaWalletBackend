import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Conversion(Base):
    """A settlement/conversion command.

    The immutable ledger remains the money source of truth; this table tracks
    command idempotency and lifecycle so retries do not duplicate ledger entries.
    """

    __tablename__ = "conversions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_conversion_user_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[ConversionStatus] = mapped_column(
        Enum(ConversionStatus), default=ConversionStatus.PENDING, nullable=False
    )

    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_requested: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    convert_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_in: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    amount_held: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    rate: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    amount_out: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
