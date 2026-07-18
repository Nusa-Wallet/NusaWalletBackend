from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import AiAuditEvent


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def record_ai_audit(
    db: Session,
    *,
    ref_type: str,
    ref_id: str,
    purpose: str,
    status: str,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    error: str | None = None,
) -> AiAuditEvent:
    response = _jsonable(response_payload)
    event = AiAuditEvent(
        ref_type=ref_type,
        ref_id=ref_id,
        purpose=purpose,
        status=status,
        model_version=response.get("model_version") if isinstance(response, dict) else None,
        request_payload=_jsonable(request_payload),
        response_payload=response,
        error=error,
    )
    db.add(event)
    return event
