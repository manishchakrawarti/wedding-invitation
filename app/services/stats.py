"""Private visitor stats for the admin page: daily counts of page views, new visitors, where they came from,
and live card previews. No personal data and no third-party tracker: just counters, kept in memory and
written to the database about once a minute."""
import logging
import re
import threading
from collections import Counter
from datetime import date
from urllib.parse import urlparse

from sqlalchemy import select

from app.config import settings

log = logging.getLogger(__name__)

BOTS = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|python|httpx|wget|headless", re.I)
VISITOR_COOKIE = "ia_v"  # "seen today" marker, so a visitor counts once a day
_pending: Counter = Counter()
_lock = threading.Lock()


def page_group(path: str) -> str:
    """'/e/priya-weds-rohan' -> '/e/*', landing and public pages as they are."""
    from app import seo

    if path in ("/", "/create", "/occasions", "/gallery", "/order", "/terms", "/privacy", "/refund"):
        return path
    if path.startswith("/wording"):
        return path
    for prefix in ("/e/", "/i/", "/o/", "/demo"):
        if path.startswith(prefix):
            return prefix.rstrip("/") + "/*"
    return path if path.strip("/") in seo.pages() else "other"


def source(referer: str, utm: str) -> str:
    """Where a visitor came from: utm_source if given, else the other site's name, else 'direct'."""
    if utm:
        return utm.lower()[:40]
    host = (urlparse(referer).hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("l.")
    own = (urlparse(settings.base_url).hostname or "").removeprefix("www.")
    if not host or host == own:
        return "direct"
    for name in ("google", "bing", "duckduckgo", "yahoo", "instagram", "facebook", "whatsapp", "youtube", "t.co", "pinterest",
                 "telegram", "linkedin", "quora", "reddit"):
        if name in host:
            return "x" if name == "t.co" else name
    return host[:40]


def track(path: str, user_agent: str, referer: str, utm: str, new_visitor: bool) -> None:
    if BOTS.search(user_agent or "") or not user_agent:
        return
    day = date.today().isoformat()
    with _lock:
        _pending[(day, "view", page_group(path))] += 1
        if new_visitor:
            _pending[(day, "visitor", "all")] += 1
            _pending[(day, "source", source(referer, utm))] += 1


def count(kind: str, key: str = "all") -> None:
    with _lock:
        _pending[(date.today().isoformat(), kind, key)] += 1


def flush() -> None:
    """Add the counts gathered since last time to the database."""
    from app.db import SessionLocal
    from app.models import DailyStat

    with _lock:
        batch = dict(_pending)
        _pending.clear()
    if not batch:
        return
    try:
        with SessionLocal() as db:
            for (day, kind, key), n in batch.items():
                row = db.scalar(select(DailyStat).where(DailyStat.day == date.fromisoformat(day), DailyStat.kind == kind,
                                                        DailyStat.key == key))
                if row is None:
                    db.add(DailyStat(day=date.fromisoformat(day), kind=kind, key=key, count=n))
                else:
                    row.count += n
            db.commit()
    except Exception:  # noqa: BLE001 — stats must never break the site; put the counts back
        log.warning("saving stats failed", exc_info=True)
        with _lock:
            _pending.update(batch)


def start_flusher(every_s: int = 60) -> None:
    def loop():
        import time

        while True:
            time.sleep(every_s)
            flush()

    threading.Thread(target=loop, name="stats", daemon=True).start()
