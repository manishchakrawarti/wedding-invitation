"""Order lifecycle: pricing, state changes and the events log."""
import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import ADDONS, PACKAGES
from app.config import settings
from app.models import Order, OrderEvent, OrderStatus, Revision, utcnow
from app.services import notify
from app.services.cards import has_rsvp
from app.utils import short_code, slugify


def log_event(db: Session, order: Order, message: str, level: str = "info") -> None:
    db.add(OrderEvent(order_id=order.id, message=message, level=level))


def set_status(db: Session, order: Order, status: OrderStatus, message: str = "") -> None:
    order.status = status.value
    log_event(db, order, message or f"Status → {status.value}")


def effective_addons(package_key: str, addons: list[str]) -> list[str]:
    """Drop add-ons the package already includes, and ones not sold at checkout."""
    pkg = PACKAGES[package_key]
    included = {"function_cards": pkg.function_cards, "rsvp": pkg.rsvp, "express": pkg.express}
    return [a for a in dict.fromkeys(addons) if a in ADDONS and ADDONS[a].selectable and not included.get(a)]


def price(package_key: str, addons: list[str], referral_ok: bool) -> tuple[int, int, int]:
    """Returns (subtotal, discount, total) in paise."""
    subtotal = PACKAGES[package_key].price * 100 + sum(ADDONS[a].price * 100 for a in effective_addons(package_key, addons))
    discount = min(settings.referral_discount_inr * 100, subtotal) if referral_ok else 0
    return subtotal, discount, subtotal - discount


def amount_for(order: Order, purpose: str) -> int:
    if purpose == "advance":
        return math.ceil(order.total * settings.advance_percent / 100 / 100) * 100  # round up to whole rupees
    if purpose == "revision":
        return ADDONS["extra_revision"].price * 100
    return order.balance_due  # full | balance


def valid_referral(db: Session, code: str) -> bool:
    code = (code or "").strip().upper()
    return bool(code) and db.scalar(select(Order.id).where(Order.referral_code == code)) is not None


def new_public_id(db: Session) -> str:
    while True:
        pid = f"{settings.order_prefix}-{date.today():%y%m}-{short_code(4)}"
        if not db.scalar(select(Order.id).where(Order.public_id == pid)):
            return pid


def new_referral_code(db: Session, bride: str) -> str:
    stem = (slugify(bride).replace("-", "")[:5] or "SHAADI").upper()
    while True:
        code = f"{stem}{short_code(3)}"
        if not db.scalar(select(Order.id).where(Order.referral_code == code)):
            return code


def ensure_rsvp_slug(db: Session, order: Order) -> None:
    if order.rsvp_slug or not has_rsvp(order):
        return
    if order.is_wedding:
        base = slugify(f"{order.bride_name}-weds-{order.groom_name}")[:60] or "wedding"
    else:
        base = slugify(f"{order.bride_name}-{order.event_type.replace('_', '-')}")[:60] or "invitation"
    slug, n = base, 1
    while db.scalar(select(Order.id).where(Order.rsvp_slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    order.rsvp_slug = slug


def preview_unlockable(order: Order) -> bool:
    """An instant preview can be paid for only when every card passed QC, so nobody pays for a broken card."""
    finals = order.live_assets("final")
    return order.status == OrderStatus.PREVIEW.value and bool(finals) and all((a.qc or {}).get("passed") for a in finals)


# --- state transitions ------------------------------------------------------

def send_proof(db: Session, order: Order, by: str = "admin") -> None:
    set_status(db, order, OrderStatus.PROOF_SENT, f"Proof v{order.current_version} sent to customer ({by})")
    db.commit()
    notify.notify_customer(db, order, "proof_ready")


def approve_proof(db: Session, order: Order) -> None:
    log_event(db, order, f"Customer approved proof v{order.current_version}")
    if order.balance_due > 0:
        set_status(db, order, OrderStatus.BALANCE_DUE, "Waiting for balance payment")
        db.commit()
        notify.notify_customer(db, order, "balance_due")
    else:
        deliver(db, order)


def request_changes(db: Session, order: Order, notes: str) -> bool:
    if order.revisions_left <= 0:
        return False
    order.revisions_used += 1
    db.add(Revision(order_id=order.id, number=order.revisions_used, notes=notes.strip()))
    set_status(db, order, OrderStatus.CHANGES_REQUESTED, f"Revision {order.revisions_used} requested: {notes.strip()[:200]}")
    db.commit()
    notify.alert_owner(db, f"Changes requested on {order.public_id}: {notes.strip()[:300]}", order)
    return True


def deliver(db: Session, order: Order) -> None:
    ensure_rsvp_slug(db, order)
    order.delivered_at = utcnow()
    set_status(db, order, OrderStatus.DELIVERED, "Final files delivered")
    db.commit()
    notify.notify_customer(db, order, "delivered")
