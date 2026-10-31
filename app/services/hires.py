"""Download sizes for instant invitations: re-rendered natively at each resolution, cached in storage."""
import io

from PIL import Image

from app.catalog import RESOLUTIONS, STYLES
from app.config import settings
from app.models import Asset, Order
from app.services.cards import cards_for_order
from app.services.overlay import CANVAS, LAYOUT_PHOTO, LAYOUT_PLAIN, add_qr, compose_card, credit_stamp, to_bytes
from app.services.storage import storage

TIERS = [r for r in sorted(RESOLUTIONS.values(), key=lambda r: r.price) if r.price > 0]


def entitled(order: Order) -> str | None:
    """Highest paid tier covered by what the customer paid (plus any coupon)."""
    credit = order.amount_paid + order.discount
    best = None
    for tier in TIERS:
        if credit >= tier.price * 100:
            best = tier.key
    return best


def allowed(order: Order, res: str) -> bool:
    if res == "free":
        return True
    best = entitled(order)
    return best is not None and RESOLUTIONS[res].price <= RESOLUTIONS[best].price


def file_info(res: str) -> tuple[str, str]:
    """(extension, content type): PNG up to Full HD, high-quality JPEG for 2K/4K so files stay phone-friendly."""
    return ("jpg", "image/jpeg") if res in ("free", "2k", "4k") else ("png", "image/png")


def render(order: Order, final: Asset, res: str) -> bytes:
    ext, _ = file_info(res)
    key = f"orders/{order.public_id}/v{final.version}/{final.card_key}_{res}.{ext}"
    if storage.exists(key):
        return storage.read(key)
    if res == "1080":
        return storage.read(final.path)
    tier = RESOLUTIONS[res]
    background = next(a for a in order.assets if a.kind == "background" and a.card_key == final.card_key
                      and a.version == final.version)
    card = next(c for c in cards_for_order(order) if c.key == final.card_key)
    layout = LAYOUT_PHOTO if (final.meta or {}).get("layout") == "photo" else LAYOUT_PLAIN
    bg = Image.open(io.BytesIO(storage.read(background.path)))
    img, _ = compose_card(bg, card.items, STYLES[card.style_key], layout, k=tier.width / CANVAS[0])
    if res == "free":
        # No RSVP QR: the invite page only goes live once a paid size is bought.
        data = to_bytes(credit_stamp(img, f"Made with love · {settings.brand_name}"), "JPEG", 88)
    else:
        if order.rsvp_slug and final.card_key == "main":
            img = add_qr(img, f"{settings.base_url}/e/{order.rsvp_slug}", STYLES[card.style_key])
        data = to_bytes(img, "JPEG", 95)
    storage.save(key, data)
    return data
