import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/fx-advisory")
def fx_advisory(base: str = "SGD", quote: str = "IDR", _: User = Depends(get_current_user)):
    """Proxy to the AI service's FX Decision-Support endpoint (Design 12
    'Rekomendasi AI'). Returns recommendation + confidence + explanation."""
    try:
        resp = httpx.get(
            f"{settings.ai_service_url}/fx/advisory",
            params={"base": base, "quote": quote},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"AI service unavailable: {exc}",
        )
