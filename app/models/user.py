from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="user")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    wallets: Mapped[list["Wallet"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    devices: Mapped[list["Device"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    notification_prefs: Mapped[list["NotificationPref"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
