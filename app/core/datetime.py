from datetime import datetime, timezone


def utc_isoformat(value: datetime) -> str:
    """Serialize a datetime as an unambiguous UTC ISO-8601 timestamp.

    SQLite returns SQLAlchemy ``DateTime`` values without timezone information,
    even when the value was originally written as UTC. Treat those legacy and
    current naive values as UTC before exposing them through the API.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
