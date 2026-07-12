import httpx
from fastapi import APIRouter, Depends

from app.core.config import settings
from app.deps import get_current_user
from app.models import User

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
