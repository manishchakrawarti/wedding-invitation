"""Orchestrator (C8) with retries and failure alerts (C10).

    paid → generate background → overlay text → QC → (owner review) → proof → final

Runs on an in-process worker pool, which is right for one server. When volume grows,
move `run_order` behind Cloud Tasks / Cloud Workflows: it is already idempotent per
order and keeps all state in the database.
"""
import io
import logging
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from sqlalchemy import select

from app.catalog import STYLES
from app.config import settings
from app.db import SessionLocal
from app.models import Asset, CostEntry, Order, OrderStatus
from app.services import notify, orders
from app.services.cards import cards_for_order
from app.services.generation import get_generator
from app.services.overlay import LAYOUT_PHOTO, LAYOUT_PLAIN, add_qr, compose_card, to_bytes, watermark
from app.services.prompts import build_prompt
from app.services.qc import run_qc
from app.services.storage import storage

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
_running: set[int] = set()
_lock = threading.Lock()

SKIP_STATUSES = {OrderStatus.PENDING_PAYMENT.value, OrderStatus.CANCELLED.value, OrderStatus.DELIVERED.value}


def enqueue(order_id: int, notes: str = "") -> None:
    if settings.run_pipeline_inline:
        run_order(order_id, notes)
    else:
        _executor.submit(run_order, order_id, notes)


def _generate_with_retry(db, order, generator, prompt, style, layout, photos, seed):
    attempts = settings.generation_max_attempts
    for attempt in range(1, attempts + 1):
        try:
            result = generator.generate(prompt, style, layout, photos, seed)
            if result.cost_inr:
                db.add(CostEntry(order_id=order.id, service=f"{result.provider}_image", units=1, cost_inr=result.cost_inr))
            return result
        except Exception as exc:  # noqa: BLE001
            orders.log_event(db, order, f"Generation attempt {attempt}/{attempts} failed: {exc}", "warn")
            db.commit()
            if attempt == attempts:
                raise
            time.sleep(settings.retry_base_delay_seconds * 2 ** (attempt - 1))


def _save(db, order, kind, card_key, version, data: bytes, ext: str, qc=None, meta=None) -> Asset:
    key = f"orders/{order.public_id}/v{version}/{card_key}_{kind}.{ext}"
    storage.save(key, data)
    asset = Asset(
        order_id=order.id, kind=kind, card_key=card_key, version=version, path=key,
        content_type="image/png" if ext == "png" else "image/jpeg", qc=qc, meta=meta,
    )
    db.add(asset)
    return asset


def run_order(order_id: int, notes: str = "") -> None:
    with _lock:
        if order_id in _running:
            return
        _running.add(order_id)
    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        if order is None or order.status in SKIP_STATUSES:
            return
        orders.ensure_rsvp_slug(db, order)
        orders.set_status(db, order, OrderStatus.GENERATING, "Design generation started" + (f" with notes: {notes[:200]}" if notes else ""))
        db.commit()

        photos = [Image.open(io.BytesIO(storage.read(a.path))) for a in order.live_assets("photo")]
        version = order.current_version + 1
        generator = get_generator()
        all_passed = True
        rsvp_url = f"{settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug else ""

        for card in cards_for_order(order):
            style = STYLES[card.style_key]
            use_photo = card.with_photo and bool(photos)
            layout = LAYOUT_PHOTO if use_photo else LAYOUT_PLAIN
            prompt = build_prompt(card.style_key, card.key, use_photo, notes)
            seed = zlib.crc32(f"{order.id}:{version}:{card.key}".encode())
            result = _generate_with_retry(db, order, generator, prompt, style, layout, photos if use_photo else [], seed)

            composed, report = compose_card(result.image, card.items, style, layout)
            qc = run_qc(card, composed, report, style, use_photo)
            final = add_qr(composed, rsvp_url, style) if rsvp_url and card.key == "main" else composed
            meta = {"title": card.title, "style": card.style_key, "provider": result.provider, "prompt": prompt}

            _save(db, order, "background", card.key, version, to_bytes(result.image, "JPEG"), "jpg", meta=meta)
            _save(db, order, "proof", card.key, version, to_bytes(watermark(final, f"PROOF · {settings.brand_name}"), "JPEG", 82), "jpg", qc, meta)
            _save(db, order, "final", card.key, version, to_bytes(final), "png", qc, meta)
            all_passed &= qc["passed"]
            orders.log_event(db, order, f"{card.title}: QC {'passed' if qc['passed'] else 'FAILED'} ({result.provider})", "info" if qc["passed"] else "warn")
            db.commit()

        order.current_version = version
        if all_passed and settings.auto_send_proof_if_qc_pass:
            orders.send_proof(db, order, by="auto")
        else:
            orders.set_status(db, order, OrderStatus.QC_REVIEW, f"Draft v{version} ready for review")
            db.commit()
            verdict = "is ready for your review" if all_passed else "FAILED automatic QC — please check"
            notify.alert_owner(db, f"Order {order.public_id} draft v{version} {verdict}.", order)
    except Exception as exc:  # noqa: BLE001
        log.exception("pipeline failed for order %s", order_id)
        db.rollback()
        order = db.get(Order, order_id)
        if order is not None:
            orders.set_status(db, order, OrderStatus.FAILED, f"Pipeline failed: {exc}")
            db.commit()
            notify.alert_owner(db, f"Order {order.public_id} failed during generation: {exc}", order)
    finally:
        db.close()
        with _lock:
            _running.discard(order_id)


def recover_stuck_orders() -> int:
    """Self-healing on startup: re-run orders a crash or redeploy left half-done."""
    with SessionLocal() as db:
        ids = db.scalars(
            select(Order.id).where(Order.status.in_([OrderStatus.QUEUED.value, OrderStatus.GENERATING.value]))
        ).all()
    for oid in ids:
        enqueue(oid)
    return len(ids)
