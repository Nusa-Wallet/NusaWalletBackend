import secrets
from datetime import datetime, timezone
from decimal import Decimal
from html import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import PaymentLink, PaymentLinkStatus, User
from app.schemas.payment_link import (
    CreatePaymentLinkRequest,
    PayLinkRequest,
    PaymentLinkResponse,
)
from app.services.ai_audit import record_ai_audit
from app.services import ledger

router = APIRouter(prefix="/payment-links", tags=["payment-links"])
public_router = APIRouter(tags=["payment-links"])


def _to_response(link: PaymentLink) -> PaymentLinkResponse:
    return PaymentLinkResponse(
        code=link.code,
        currency=link.currency,
        amount=link.amount,
        note=link.note,
        status=link.status.value,
        url=f"/pay/{link.code}",
    )


@router.post("", response_model=PaymentLinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: CreatePaymentLinkRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merchant issues a payment link in a target currency (Design 10/11)."""
    link = PaymentLink(
        code=secrets.token_urlsafe(8),
        merchant_user_id=current.id,
        currency=payload.currency.upper(),
        amount=payload.amount,
        note=payload.note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _to_response(link)


@router.get("/{code}", response_model=PaymentLinkResponse)
def get_link(code: str, db: Session = Depends(get_db)):
    """Public — payer opens this in a browser, no app/login needed."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    return _to_response(link)


def _public_checkout_html(link: PaymentLink, request: Request) -> str:
    amount = f"{Decimal(link.amount):,.2f}"
    currency = escape(link.currency)
    note = escape(link.note or "Pembayaran layanan digital")
    status_label = escape(link.status.value.replace("_", " ").title())
    pay_endpoint = str(request.url_for("pay_link", code=link.code))
    disabled = "disabled" if link.status != PaymentLinkStatus.PENDING else ""
    button_label = "Bayar Sandbox" if link.status == PaymentLinkStatus.PENDING else status_label
    return f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NusaWallet Payment Link</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f8fb;
      color: #172033;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    main {{
      width: min(440px, 100%);
      background: #ffffff;
      border: 1px solid #dbe3ef;
      border-radius: 14px;
      box-shadow: 0 18px 44px rgba(23, 32, 51, 0.12);
      overflow: hidden;
    }}
    header {{
      padding: 22px 24px;
      background: #0f766e;
      color: white;
    }}
    .brand {{ font-size: 13px; font-weight: 700; opacity: 0.9; }}
    h1 {{ margin: 10px 0 0; font-size: 25px; line-height: 1.15; }}
    section {{ padding: 24px; }}
    .amount {{ font-size: 34px; font-weight: 800; letter-spacing: 0; }}
    .muted {{ color: #64748b; font-size: 14px; line-height: 1.5; }}
    .status {{
      display: inline-flex;
      margin-top: 14px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #ecfdf5;
      color: #047857;
      font-size: 12px;
      font-weight: 700;
    }}
    label {{ display: block; margin-top: 16px; font-size: 13px; font-weight: 700; }}
    input {{
      width: 100%;
      box-sizing: border-box;
      height: 46px;
      margin-top: 7px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 0 12px;
      font-size: 15px;
    }}
    button {{
      width: 100%;
      height: 48px;
      margin-top: 20px;
      border: 0;
      border-radius: 8px;
      background: #0f766e;
      color: #ffffff;
      font-size: 15px;
      font-weight: 800;
      cursor: pointer;
    }}
    button:disabled {{ background: #94a3b8; cursor: not-allowed; }}
    #result {{ margin-top: 16px; font-size: 14px; line-height: 1.45; }}
    .ok {{ color: #047857; }}
    .warn {{ color: #b45309; }}
    .bad {{ color: #b91c1c; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="brand">NusaWallet Sandbox Checkout</div>
      <h1>Payment Link</h1>
    </header>
    <section>
      <div class="amount">{currency} {amount}</div>
      <p class="muted">{note}</p>
      <span class="status">{status_label}</span>

      <form id="pay-form">
        <label for="payer_name">Nama pembayar</label>
        <input id="payer_name" name="payer_name" value="Client Demo" required {disabled}>
        <label for="origin_country">Negara asal</label>
        <input id="origin_country" name="origin_country" value="SG" maxlength="2" {disabled}>
        <button type="submit" {disabled}>{button_label}</button>
      </form>
      <div id="result" class="muted">Transaksi ini berjalan di sandbox dan tidak memindahkan dana nyata.</div>
    </section>
  </main>
  <script>
    const form = document.getElementById("pay-form");
    const result = document.getElementById("result");
    form?.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const button = form.querySelector("button");
      button.disabled = true;
      button.textContent = "Memproses...";
      try {{
        const response = await fetch("{pay_endpoint}", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            payer_name: document.getElementById("payer_name").value,
            origin_country: document.getElementById("origin_country").value,
            idempotency_key: "checkout-{escape(link.code)}"
          }})
        }});
        const data = await response.json();
        if (response.ok) {{
          result.className = "ok";
          result.textContent = `Pembayaran diterima. Risiko: ${{data.risk_level ?? "LOW"}}.`;
          button.textContent = "Sudah Dibayar";
        }} else if (data.detail?.status === "REVIEW_REQUIRED") {{
          result.className = "warn";
          result.textContent = `Pembayaran ditahan untuk review. Risiko: ${{data.detail.risk_level ?? "HIGH"}}.`;
          button.textContent = "Ditahan Review";
        }} else {{
          result.className = "bad";
          result.textContent = data.detail ?? "Pembayaran gagal diproses.";
          button.disabled = false;
          button.textContent = "Coba Lagi";
        }}
      }} catch {{
        result.className = "bad";
        result.textContent = "Server tidak dapat dijangkau.";
        button.disabled = false;
        button.textContent = "Coba Lagi";
      }}
    }});
  </script>
</body>
</html>"""


@public_router.get("/pay/{code}", response_class=HTMLResponse, name="public_payment_checkout")
def public_payment_checkout(code: str, request: Request, db: Session = Depends(get_db)):
    """Public browser checkout for sandbox payment links."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    return HTMLResponse(_public_checkout_html(link, request))


def _fraud_score(
    link: PaymentLink,
    payer_name: str,
    origin_country: str | None,
    is_new_payer: bool,
) -> tuple[dict, dict, str, str | None]:
    """Best-effort call to the AI fraud service with full transaction context.

    Never blocks the demo if the AI service is down — returns an explicit benign
    fallback (LOW / ALLOW) so the payment flow can still proceed."""
    payload = {
        "transaction_id": link.code,
        "amount": float(link.amount),
        "currency": link.currency,
        "payer_name": payer_name,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "is_new_payer": is_new_payer,
    }
    if origin_country:
        payload["origin_country"] = origin_country.upper()
    try:
        resp = httpx.post(f"{settings.ai_service_url}/fraud/score", json=payload, timeout=3.0)
        resp.raise_for_status()
        return payload, resp.json(), "SUCCESS", None
    except Exception as exc:
        return payload, {
            "risk_score": 0.0, "risk_level": "LOW", "flagged": False,
            "recommended_action": "ALLOW", "factors": [], "reason": "ai-service-unavailable",
        }, "FALLBACK", str(exc)


def _transition_link(link: PaymentLink, target: PaymentLinkStatus) -> None:
    allowed = {
        PaymentLinkStatus.PENDING: {
            PaymentLinkStatus.PAID,
            PaymentLinkStatus.REVIEW_REQUIRED,
            PaymentLinkStatus.EXPIRED,
        },
        PaymentLinkStatus.PAID: set(),
        PaymentLinkStatus.REVIEW_REQUIRED: set(),
        PaymentLinkStatus.EXPIRED: set(),
    }
    if link.status == target:
        return
    if target not in allowed[link.status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition payment link from {link.status.value} to {target.value}",
        )
    link.status = target


def _paid_response(link: PaymentLink) -> dict:
    return {
        "status": "PAID",
        "credited": link.amount,
        "currency": link.currency,
        "risk_score": link.risk_score,
        "risk_level": link.risk_level,
        "idempotent": True,
    }


def _review_required_error(link: PaymentLink, factors: list[str] | None = None) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "status": "REVIEW_REQUIRED",
            "risk_score": link.risk_score,
            "risk_level": link.risk_level,
            "factors": factors or [],
            "idempotent": True,
        },
    )


@router.post("/{code}/pay")
def pay_link(code: str, payload: PayLinkRequest, db: Session = Depends(get_db)):
    """Simulate an international payer paying the link. On success, the merchant's
    foreign-currency wallet is CREDITED (proposal step 2-3)."""
    link = db.query(PaymentLink).filter(PaymentLink.code == code).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment link not found")
    if link.status == PaymentLinkStatus.PAID:
        return _paid_response(link)
    if link.status == PaymentLinkStatus.REVIEW_REQUIRED:
        raise _review_required_error(link)
    if link.status != PaymentLinkStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Link is {link.status.value}")

    # Has this merchant been paid by this payer before? (first-time payer is riskier)
    is_new_payer = (
        db.query(PaymentLink)
        .filter(
            PaymentLink.merchant_user_id == link.merchant_user_id,
            PaymentLink.payer_name == payload.payer_name,
            PaymentLink.status == PaymentLinkStatus.PAID,
        )
        .first()
        is None
    )

    fraud_request, fraud, audit_status, audit_error = _fraud_score(
        link,
        payload.payer_name,
        payload.origin_country,
        is_new_payer,
    )
    record_ai_audit(
        db,
        ref_type="payment_link",
        ref_id=link.code,
        purpose="fraud_score",
        status=audit_status,
        request_payload=fraud_request,
        response_payload=fraud,
        error=audit_error,
    )
    link.risk_score = float(fraud.get("risk_score") or 0.0)
    link.risk_level = fraud.get("risk_level")
    link.payer_name = payload.payer_name

    # HIGH risk / REVIEW_REQUIRED holds the payment for manual review — not credited.
    needs_review = fraud.get("recommended_action") == "REVIEW_REQUIRED" or fraud.get("flagged")
    if needs_review:
        _transition_link(link, PaymentLinkStatus.REVIEW_REQUIRED)
        db.commit()
        raise _review_required_error(link, fraud.get("factors", []))

    wallet = ledger.get_or_create_wallet(db, link.merchant_user_id, link.currency)
    db.flush()
    ledger.record_external_credit(
        db, wallet, link.amount, "payment_link", link.code,
        f"Payment from {payload.payer_name}",
    )
    _transition_link(link, PaymentLinkStatus.PAID)
    link.paid_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "PAID", "credited": link.amount, "currency": link.currency,
        "risk_score": link.risk_score, "risk_level": link.risk_level, "fraud": fraud,
    }
