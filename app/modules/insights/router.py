from collections import Counter
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.datetime import utc_isoformat
from app.deps import get_current_user
from app.models import LedgerEntry, PaymentLink, User, Wallet
from app.services import ledger

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/fx-advisory")
def fx_advisory(
    base: str = "SGD",
    quote: str = "IDR",
    amount: float | None = None,
    horizon_days: int = 7,
    risk_preference: str = "MODERATE",
    _: User = Depends(get_current_user),
):
    """Proxy to the AI service's FX decision engine (Design 12 'Rekomendasi AI').

    Forwards amount, horizon, and risk preference and passes the full response through
    (action / confidence / split percentage / gain-loss / rationale). Falls back to an
    explicit neutral advisory if the AI service is unavailable, so the UI still renders."""
    params: dict = {
        "base": base, "quote": quote,
        "horizon_days": horizon_days, "risk_preference": risk_preference,
    }
    if amount is not None:
        params["amount"] = amount
    try:
        resp = httpx.get(f"{settings.ai_service_url}/fx/advisory", params=params, timeout=6.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {
            "pair": f"{base.upper()}/{quote.upper()}",
            "action": "CONVERT_NOW",
            "confidence": 0.0,
            "recommended_convert_percentage": 100,
            "rationale": "Layanan AI sedang tidak tersedia; gunakan kurs saat ini.",
            "reasons": ["AI service unavailable"],
            "model_version": "unavailable",
        }


_FACTOR_LABELS: dict[str, str] = {
    "high_amount_ratio": "Jumlah transaksi jauh di atas rata-rata",
    "high_amount_zscore": "Jumlah transaksi tidak normal secara statistik",
    "odd_hour": "Waktu transaksi di luar jam aktivitas normal",
    "low_name_quality": "Nama pengirim tidak dikenal atau tidak lengkap",
    "payer_velocity_burst": "Beberapa transaksi dalam waktu singkat",
    "duplicate_payment": "Pembayaran duplikat terdeteksi",
    "new_payer_high_amount": "Pengirim baru dengan jumlah besar",
    "high_risk_country": "Negara asal berisiko tinggi",
    "currency_deviation": "Mata uang tidak biasa digunakan",
    "country_deviation": "Negara asal tidak biasa",
}

_FACTOR_RECOMMENDATIONS: dict[str, dict] = {
    "high_amount_ratio": {
        "title": "Limit Transaksi Besar",
        "desc": "Tetapkan batas maksimum transaksi harian",
        "bg": "#EFF6FF", "iconColor": "#2563EB",
    },
    "odd_hour": {
        "title": "Verifikasi Waktu Tidak Biasa",
        "desc": "Aktifkan notifikasi untuk transaksi di luar jam aktif",
        "bg": "#FFF7ED", "iconColor": "#D97706",
    },
    "high_risk_country": {
        "title": "Blokir Negara Berisiko",
        "desc": "Batasi transaksi dari negara dengan risiko tinggi",
        "bg": "#FEF2F2", "iconColor": "#E7000B",
    },
    "currency_deviation": {
        "title": "Pantau Mata Uang Baru",
        "desc": "Waspadai transaksi menggunakan mata uang yang tidak biasa",
        "bg": "#FAF5FF", "iconColor": "#7C3AED",
    },
}

_GENERAL_RECOMMENDATIONS = [
    {
        "title": "Aktifkan Verifikasi Tambahan",
        "desc": "Verifikasi identitas sebelum menyetujui transaksi",
        "bg": "#EFF6FF", "iconColor": "#2563EB",
    },
    {
        "title": "Tunda Penarikan",
        "desc": "Tahan dana selama 24-48 jam untuk ditinjau",
        "bg": "#FFF7ED", "iconColor": "#D97706",
    },
    {
        "title": "Aktifkan Review Manual",
        "desc": "Setujui secara manual untuk transaksi besar",
        "bg": "#FAF5FF", "iconColor": "#7C3AED",
    },
]


@router.get("/fraud-analysis")
def fraud_analysis(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet_ids = [w.id for w in db.query(Wallet).filter(Wallet.user_id == current.id).all()]
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.wallet_id.in_(wallet_ids))
        .order_by(LedgerEntry.created_at.desc())
        .limit(50)
        .all()
    ) if wallet_ids else []

    if not entries:
        debits = []
        all_entries = []
    else:
        all_entries = [
            {
                "id": e.id, "currency": e.currency,
                "direction": e.direction.value, "amount": float(e.amount),
                "ref_type": e.ref_type, "description": e.description,
                "created_at": utc_isoformat(e.created_at),
                "hour": e.created_at.hour,
            }
            for e in entries
        ]
        debits = [e for e in all_entries if e["direction"] == "DEBIT"]

    if not debits:
        return {
            "has_data": False,
            "message": "Belum ada transaksi untuk dianalisis.",
        }

    flagged = max(debits, key=lambda e: e["amount"])

    amounts = [e["amount"] for e in debits]
    avg_amount = sum(amounts) / len(amounts)
    currencies = [e["currency"] for e in debits]
    hours = [e["hour"] for e in debits]

    normal_hours = [h for h in hours if 6 <= h <= 23]
    if normal_hours:
        hour_min = min(normal_hours)
        hour_max = max(normal_hours)
        active_hours = f"{hour_min}:00 – {hour_max}:00"
    else:
        active_hours = "Tidak ada data"

    top_currency = Counter(currencies).most_common(1)[0][0] if currencies else "IDR"

    now = datetime.now(timezone.utc)
    payload = {
        "transaction_id": str(flagged["id"]),
        "amount": flagged["amount"],
        "currency": flagged["currency"],
        "payer_name": current.full_name,
        "occurred_at": now.isoformat(),
        "hour": flagged["hour"],
        "user_id": current.id,
        "transactions_last_24h": len([e for e in debits if e["hour"] == flagged["hour"]]),
    }

    try:
        resp = httpx.post(f"{settings.ai_service_url}/fraud/score", json=payload, timeout=3.0)
        resp.raise_for_status()
        fraud_data = resp.json()
    except Exception:
        fraud_data = {
            "risk_score": 0.0, "risk_level": "LOW", "flagged": False,
            "recommended_action": "ALLOW", "factors": [],
        }

    risk_score_pct = round(fraud_data.get("risk_score", 0) * 100)

    raw_factors: list[str] = fraud_data.get("factors", [])
    factors = []
    for f in raw_factors:
        factors.append({
            "key": f,
            "label": _FACTOR_LABELS.get(f, f.replace("_", " ").title()),
        })

    recommendations = []
    for f in raw_factors:
        rec = _FACTOR_RECOMMENDATIONS.get(f)
        if rec:
            recommendations.append(rec)
    for gr in _GENERAL_RECOMMENDATIONS:
        if gr not in recommendations:
            recommendations.append(gr)

    return {
        "has_data": True,
        "risk_score": risk_score_pct,
        "risk_level": fraud_data.get("risk_level", "LOW"),
        "flagged": fraud_data.get("flagged", False),
        "recommended_action": fraud_data.get("recommended_action", "ALLOW"),
        "factors": factors,
        "transaction": {
            "id": flagged["id"],
            "amount": f"{flagged['amount']:,.2f}",
            "currency": flagged["currency"],
            "direction": flagged["direction"],
            "description": flagged.get("description") or flagged.get("ref_type", ""),
            "created_at": flagged["created_at"],
        },
        "normal_activity": {
            "avg_amount": round(avg_amount, 2),
            "avg_amount_display": f"{avg_amount:,.2f}",
            "top_currency": top_currency,
            "currencies": sorted(set(currencies)),
            "active_hours": active_hours,
            "total_transactions": len(debits),
        },
        "suspicious_activity": {
            "amount": f"{flagged['amount']:,.2f}",
            "currency": flagged["currency"],
            "time": f"{flagged['hour']:02d}:00",
            "is_unusual_amount": flagged["amount"] > avg_amount * 3,
            "is_odd_hour": flagged["hour"] < 6 or flagged["hour"] >= 23,
            "is_unusual_currency": flagged["currency"] != top_currency,
        },
        "recommendations": recommendations,
    }
