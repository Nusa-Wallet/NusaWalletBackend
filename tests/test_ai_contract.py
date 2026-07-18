"""Phase 13 contract tests between the core backend and the AI service.

The AI HTTP calls are mocked with contract-shaped (CONTRACTS.md) responses; the tests
assert the backend sends the agreed request fields and handles the responses correctly
(fraud storage + REVIEW_REQUIRED mapping + fallback, FX passthrough, conversion split).
Uses an in-memory SQLite DB and overridden auth so no live services are needed.
"""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    EntryDirection,
    LedgerEntry,
    PaymentLink,
    PaymentLinkStatus,
    User,
    Wallet,
)
from app.services import ledger

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _resp(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = payload
    mock.raise_for_status.return_value = None
    return mock


class BackendAiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        db = TestingSession()
        db.add(User(email="m@x.id", full_name="Merchant", hashed_password="x"))
        db.commit()
        cls.user_id = db.query(User).first().id
        db.close()

        def override_db():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        def override_user():
            db = TestingSession()
            try:
                return db.query(User).first()
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _create_link(self, amount="100", currency="SGD") -> str:
        r = self.client.post("/payment-links", json={"currency": currency, "amount": amount})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["code"]

    def test_payment_link_returns_public_checkout_url(self):
        code = self._create_link(amount="250", currency="SGD")
        detail = self.client.get(f"/payment-links/{code}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["url"], f"/pay/{code}")

        checkout = self.client.get(f"/pay/{code}")
        self.assertEqual(checkout.status_code, 200, checkout.text)
        self.assertIn("NusaWallet Sandbox Checkout", checkout.text)
        self.assertIn("SGD", checkout.text)

    def _signed_totals_by_currency(self, ref_id: str) -> dict[str, Decimal]:
        db = TestingSession()
        try:
            totals: dict[str, Decimal] = {}
            for entry in db.query(LedgerEntry).filter(LedgerEntry.ref_id == ref_id).all():
                sign = Decimal(1) if entry.direction == EntryDirection.CREDIT else Decimal(-1)
                totals.setdefault(entry.currency, Decimal("0"))
                totals[entry.currency] += sign * Decimal(entry.amount)
            return totals
        finally:
            db.close()

    def _ledger_entry_count(self, ref_id: str) -> int:
        db = TestingSession()
        try:
            return db.query(LedgerEntry).filter(LedgerEntry.ref_id == ref_id).count()
        finally:
            db.close()

    # --- FX proxy ---------------------------------------------------------
    @patch("app.modules.insights.router.httpx.get")
    def test_fx_proxy_forwards_params_and_passes_through(self, mock_get):
        mock_get.return_value = _resp({
            "pair": "SGD/IDR", "action": "SPLIT_CONVERSION", "confidence": 0.6,
            "recommended_convert_percentage": 40, "model_version": "fx-decision-1.0.0", "reasons": [],
        })
        r = self.client.get("/insights/fx-advisory", params={
            "base": "SGD", "quote": "IDR", "amount": 1000, "horizon_days": 7, "risk_preference": "CONSERVATIVE",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["action"], "SPLIT_CONVERSION")
        sent = mock_get.call_args.kwargs["params"]
        self.assertEqual(sent["amount"], 1000)
        self.assertEqual(sent["horizon_days"], 7)
        self.assertEqual(sent["risk_preference"], "CONSERVATIVE")

    @patch("app.modules.insights.router.httpx.get", side_effect=RuntimeError("down"))
    def test_fx_proxy_falls_back_when_ai_unavailable(self, _):
        r = self.client.get("/insights/fx-advisory", params={"base": "SGD", "quote": "IDR"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["model_version"], "unavailable")
        self.assertEqual(r.json()["action"], "CONVERT_NOW")

    # --- Fraud ------------------------------------------------------------
    @patch("app.modules.payment_link.router.httpx.post")
    def test_fraud_sends_full_context_and_low_risk_credits(self, mock_post):
        mock_post.return_value = _resp({
            "risk_score": 0.1, "risk_level": "LOW", "flagged": False,
            "recommended_action": "ALLOW", "factors": [],
        })
        code = self._create_link()
        r = self.client.post(f"/payment-links/{code}/pay",
                             json={"payer_name": "John Doe", "origin_country": "SG"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "PAID")
        self.assertEqual(r.json()["risk_level"], "LOW")
        self.assertEqual(self._signed_totals_by_currency(code), {"SGD": Decimal("0.0000")})
        self.assertEqual(self._ledger_entry_count(code), 2)
        retry = self.client.post(f"/payment-links/{code}/pay",
                                 json={"payer_name": "John Doe", "origin_country": "SG"})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()["idempotent"])
        self.assertEqual(self._ledger_entry_count(code), 2)
        sent = mock_post.call_args.kwargs["json"]
        for key in ("transaction_id", "amount", "currency", "payer_name", "occurred_at", "is_new_payer"):
            self.assertIn(key, sent)  # CONTRACTS.md request fields
        self.assertEqual(sent["origin_country"], "SG")
        self.assertTrue(sent["is_new_payer"])

    @patch("app.modules.payment_link.router.httpx.post")
    def test_fraud_high_risk_holds_for_review_and_stores(self, mock_post):
        mock_post.return_value = _resp({
            "risk_score": 0.9, "risk_level": "HIGH", "flagged": True,
            "recommended_action": "REVIEW_REQUIRED", "factors": ["Nominal besar"],
        })
        code = self._create_link(amount="999999")
        r = self.client.post(f"/payment-links/{code}/pay",
                             json={"payer_name": "", "origin_country": "KP"})
        self.assertEqual(r.status_code, 402)
        detail = r.json()["detail"]
        self.assertEqual(detail["status"], "REVIEW_REQUIRED")
        self.assertEqual(detail["risk_level"], "HIGH")
        db = TestingSession()
        link = db.query(PaymentLink).filter_by(code=code).first()
        self.assertEqual(link.status, PaymentLinkStatus.REVIEW_REQUIRED)
        self.assertEqual(link.risk_level, "HIGH")
        self.assertAlmostEqual(link.risk_score, 0.9)
        db.close()

    @patch("app.modules.payment_link.router.httpx.post", side_effect=RuntimeError("down"))
    def test_fraud_fallback_still_credits(self, _):
        code = self._create_link()
        r = self.client.post(f"/payment-links/{code}/pay", json={"payer_name": "Jane Roe"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "PAID")

    # --- Conversion split -------------------------------------------------
    def test_conversion_accepts_split_percentage(self):
        db = TestingSession()
        wallet = Wallet(user_id=self.user_id, currency="USD")
        db.add(wallet)
        db.flush()
        ledger.record_external_credit(db, wallet, Decimal("1000"), "seed", "conversion-test-seed")
        db.commit()
        db.close()
        with patch("app.services.fx.get_rate", return_value=Decimal("16000")):
            r = self.client.post("/settlement/convert", json={
                "from_currency": "USD",
                "to_currency": "IDR",
                "amount": "1000",
                "convert_percentage": 40,
                "idempotency_key": "convert-usd-idr-40",
            })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        ref_id = f"conv-{body['transaction_id']}"
        self.assertEqual(body["convert_percentage"], 40)
        self.assertEqual(body["status"], "COMPLETED")
        self.assertEqual(float(body["amount_in"]), 400.0)     # 40% converted now
        self.assertEqual(float(body["amount_held"]), 600.0)   # 60% held
        self.assertEqual(
            self._signed_totals_by_currency(ref_id),
            {"USD": Decimal("0.0000"), "IDR": Decimal("0.0000")},
        )
        self.assertEqual(self._ledger_entry_count(ref_id), 5)
        retry = self.client.post("/settlement/convert", json={
            "from_currency": "USD",
            "to_currency": "IDR",
            "amount": "1000",
            "convert_percentage": 40,
            "idempotency_key": "convert-usd-idr-40",
        })
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()["idempotent"])
        self.assertEqual(retry.json()["transaction_id"], body["transaction_id"])
        self.assertEqual(self._ledger_entry_count(ref_id), 5)


if __name__ == "__main__":
    unittest.main()
