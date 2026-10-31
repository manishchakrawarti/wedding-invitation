"""Safe online backup of the SQLite database (works while the app is running). Keeps the newest 14.

    docker compose exec -T app python scripts/backup_sqlite.py      # VPS, e.g. from a daily cron job
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

KEEP = 14


def main() -> int:
    db = settings.data_dir / "app.db"
    if not db.exists():
        print(f"No database at {db}")
        return 1
    folder = settings.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"app-{datetime.now():%Y%m%d-%H%M}.db"
    with sqlite3.connect(db) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    for old in sorted(folder.glob("app-*.db"))[:-KEEP]:
        old.unlink()
    print(f"Backed up to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
