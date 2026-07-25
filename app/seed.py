"""Seed demo users with balances and transaction history.

Run:  python -m app.seed

Credentials:
  john.doe@example.com / password123
  sarah.wijaya@example.com / password123
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from random import randint, uniform

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Device, NotificationPref, User, EntryDirection
from app.services import ledger


def _seed_user(db, email, full_name, phone, balances, tx_count=6, role="user"):
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            phone=phone,
            hashed_password=hash_password("password123"),
            role=role,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created user {email} / password123 ({full_name})")

    for ccy, amount in balances.items():
        wallet = ledger.get_or_create_wallet(db, user.id, ccy)
        db.flush()
        if ledger.get_balance(db, wallet.id) == 0:
            ledger.record_external_credit(
                db, wallet, amount, "topup",
                description="Initial demo balance",
            )

    now = datetime.now(timezone.utc)
    tx_specs = [
        ("Upwork", "CREDIT", Decimal("450.00"), "USD"),
        ("Konversi USD\u2192IDR", "DEBIT", Decimal("200.00"), "USD"),
        ("Fiverr", "CREDIT", Decimal("120.00"), "USD"),
        ("Transfer ke Tabungan", "DEBIT", Decimal("500.00"), "IDR"),
        ("Freelance Project", "CREDIT", Decimal("750.00"), "EUR") if "EUR" in balances else ("Payment", "DEBIT", Decimal("100.00"), "USD"),
        ("Top Up", "CREDIT", Decimal("250.00"), "SGD") if "SGD" in balances else ("Subscription", "DEBIT", Decimal("15.00"), "USD"),
    ]

    for i in range(tx_count):
        label, direction, amt, ccy = tx_specs[i % len(tx_specs)]
        wallet = ledger.get_or_create_wallet(db, user.id, ccy)
        db.flush()
        entry = ledger.post_entry(
            db, wallet,
            EntryDirection.CREDIT if direction == "CREDIT" else EntryDirection.DEBIT,
            amt, "topup" if direction == "CREDIT" else "payment",
            description=label,
        )
        entry.created_at = now - timedelta(days=i * 2 + 1, hours=randint(0, 23))

    if not db.query(Device).filter(Device.user_id == user.id).first():
        devices_data = [
            Device(user_id=user.id, name="iPhone 15 Pro", os="iOS 18.2", last_active=now, is_current=True),
            Device(user_id=user.id, name="Chrome - Windows", os="Windows 11", last_active=now - timedelta(hours=2), is_current=False),
        ]
        for d in devices_data:
            db.add(d)

    if not db.query(NotificationPref).filter(NotificationPref.user_id == user.id).first():
        pref_keys = ["push", "email", "conversion", "payment", "fraud", "insights", "promo"]
        for key in pref_keys:
            db.add(NotificationPref(user_id=user.id, key=key, push=True, email=key != "promo"))

    db.commit()
    print(f"  Balances: {', '.join(f'{c}={v}' for c, v in balances.items())}")
    print(f"  Transactions: {tx_count}")


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        old = db.query(User).filter(User.email == "demo@nusawallet.id").first()
        if old:
            db.delete(old)
            db.commit()
            print("Removed old demo user (demo@nusawallet.id)")

        _seed_user(
            db, "john.doe@example.com", "John Doe", "081234567890",
            balances={"IDR": Decimal("75000000"), "USD": Decimal("2500"), "EUR": Decimal("1200")},
            role="admin",
        )
        _seed_user(
            db, "sarah.wijaya@example.com", "Sarah Wijaya", "082345678901",
            balances={"IDR": Decimal("45000000"), "USD": Decimal("1800"), "SGD": Decimal("2100")},
        )
        print("\nSeed complete!")
        print("  john.doe@example.com / password123")
        print("  sarah.wijaya@example.com / password123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
