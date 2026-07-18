"""Reset the local SQLite demo database and seed the demo user.

This is intentionally limited to SQLite files so it cannot wipe a deployed
database by accident.

Run from NusaWalletBackend:
    python scripts/reset_demo_db.py
"""

from pathlib import Path

from app.core.config import settings
from app.seed import run as seed


def _sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("reset_demo_db.py only supports local sqlite:/// databases")
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def main() -> None:
    db_path = _sqlite_path(settings.database_url)
    if db_path.exists():
        db_path.unlink()
        print(f"Removed {db_path}")
    else:
        print(f"No existing DB at {db_path}")
    seed()
    print("Demo database reset complete.")


if __name__ == "__main__":
    main()
