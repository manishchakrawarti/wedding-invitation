"""Retention cleanup and sample images."""
import logging
import threading
import time
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import STYLES
from app.config import APP_DIR, settings
from app.models import Asset, Order, utcnow
from app.services.cards import main_card
from app.services.generation import offline_generator
from app.services.overlay import LAYOUT_PLAIN, compose_card, to_bytes
from app.services.storage import storage

log = logging.getLogger(__name__)
SAMPLE_DIR = settings.data_dir / "samples"
CUSTOM_SAMPLE_DIR = APP_DIR / "static" / "samples"  # drop real AI samples here to override


def cleanup_expired(db: Session) -> dict:
    """Delete customer photos after photo_retention_days, and all files of delivered
    orders after final_retention_days. Database rows stay (marked deleted) for accounting."""
    now = utcnow()
    photo_cutoff = now - timedelta(days=settings.photo_retention_days)
    final_cutoff = now - timedelta(days=settings.final_retention_days)
    photos = db.scalars(
        select(Asset).join(Order).where(
            Asset.deleted_at.is_(None), Asset.created_at < photo_cutoff,
            (Asset.kind == "photo") | (Asset.kind.in_(["portrait", "portrait_raw"]) & Order.delivered_at.is_(None)),
        )
    ).all()
    old_files = db.scalars(
        select(Asset).join(Order).where(Asset.deleted_at.is_(None), Order.delivered_at.is_not(None), Order.delivered_at < final_cutoff)
    ).all()
    removed = 0
    for asset in {a.id: a for a in [*photos, *old_files]}.values():
        storage.delete(asset.path)
        asset.deleted_at = now
        removed += 1
    db.commit()
    return {"photos": len(photos), "files_removed": removed}


def start_daily_cleanup() -> None:
    from app.db import SessionLocal

    def loop() -> None:
        while True:
            try:
                with SessionLocal() as db:
                    result = cleanup_expired(db)
                if result["files_removed"]:
                    log.info("retention cleanup: %s", result)
            except Exception:  # noqa: BLE001
                log.exception("cleanup failed")
            time.sleep(24 * 3600)

    threading.Thread(target=loop, name="cleanup", daemon=True).start()


DEMO = dict(
    language="en", package="basic", addons=[], bride_name="Ananya", groom_name="Arjun",
    bride_name_local="", groom_name_local="", bride_family="", groom_family="",
    wedding_date=date(2026, 12, 12), venue_name="The Royal Palace Gardens", venue_address="", city="Jaipur",
    functions=[{"key": "wedding", "time": "19:30"}],
)


def sample_image(style_key: str) -> bytes:
    """Gallery image for a style: your own file in static/samples if present, otherwise generated once and cached."""
    for ext in ("jpg", "png", "webp"):
        custom = CUSTOM_SAMPLE_DIR / f"{style_key}.{ext}"
        if custom.exists():
            return custom.read_bytes()
    cached = SAMPLE_DIR / f"{style_key}.jpg"
    if cached.exists():
        return cached.read_bytes()
    style = STYLES[style_key]
    demo = SimpleNamespace(**DEMO, style=style_key)
    if style_key == "muslim_nikah":
        demo.bride_name, demo.groom_name, demo.functions = "Zoya", "Ayaan", [{"key": "nikah", "time": "19:30"}]
    elif style_key == "christian":
        demo.bride_name, demo.groom_name = "Grace", "Daniel"
    card = main_card(demo)
    bg = offline_generator().generate("", style, LAYOUT_PLAIN, [], seed=7).image
    img, _ = compose_card(bg, card.items, style, LAYOUT_PLAIN)
    data = to_bytes(img.resize((720, 900)), "JPEG", 85)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data
