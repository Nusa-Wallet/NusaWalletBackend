"""Seed a demo user with some balances so the mobile app has data on first run.

Run:  python -m app.seed
Login: demo@nusawallet.id / password123
"""

from decimal import Decimal

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import User
from app.services import ledger


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@nusawallet.id").first()
        if user is None:
            user = User(
                email="demo@nusawallet.id",
                full_name="Andi Rizky",
                phone="081234567890",
                hashed_password=hash_password("password123"),
                is_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print("Created demo user demo@nusawallet.id / password123")

        # Give starting balances (matches the UI mockups).
        seed_balances = {"IDR": Decimal("63500000"), "USD": Decimal("1520"), "SGD": Decimal("980")}
        for ccy, amount in seed_balances.items():
            wallet = ledger.get_or_create_wallet(db, user.id, ccy)
            db.flush()
            if ledger.get_balance(db, wallet.id) == 0:
                ledger.record_external_credit(
                    db,
                    wallet,
                    amount,
                    "topup",
                    description="Initial demo balance",
                )
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
