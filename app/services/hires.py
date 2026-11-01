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
    """Highest paid tier covered by what the customer paid (plus any coupon).
    Done-for-you orders that are fully paid get every size."""
    if order.source not in ("instant", "test") and order.amount_paid and order.balance_due == 0:
        return TIERS[-1].key
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
    img, card = _compose(order, final, tier.width)
    if res == "free":
        # No RSVP QR: the invite page only goes live once a paid size is bought.
        data = to_bytes(credit_stamp(img, f"Made with love · {settings.brand_name}"), "JPEG", 88)
    else:
        if order.rsvp_slug and final.card_key == "main":
            img = add_qr(img, f"{settings.base_url}/e/{order.rsvp_slug}", STYLES[card.style_key])
        data = to_bytes(img, "JPEG", 95)
    storage.save(key, data)
    return data


def _compose(order: Order, final: Asset, width: int):
    """The card drawn natively at this width from its background (no QR, no credit), and its card spec."""
    background = next(a for a in order.assets if a.kind == "background" and a.card_key == final.card_key
                      and a.version == final.version)
    card = next(c for c in cards_for_order(order) if c.key == final.card_key)
    layout = LAYOUT_PHOTO if (final.meta or {}).get("layout") == "photo" else LAYOUT_PLAIN
    bg = Image.open(io.BytesIO(storage.read(background.path)))
    img, _ = compose_card(bg, card.items, STYLES[card.style_key], layout, k=width / CANVAS[0])
    return img, card


def personal_tier(order: Order) -> str:
    """Size of a guest's personal card: Full HD once bought, else the free size."""
    from app.models import OrderStatus

    return "1080" if order.status == OrderStatus.DELIVERED.value and allowed(order, "1080") else "free"


def render_personal(order: Order, final: Asset, invitee) -> bytes:
    """The card with 'Specially for <guest>' on it. Full HD with a QR to the guest's own invite link once a size
    is bought, else the free size with its small credit. Not stored: one per guest would fill the disk."""
    from app import i18n
    from app.services import invites
    from app.services.overlay import name_ribbon

    res = personal_tier(order)
    img, card = _compose(order, final, RESOLUTIONS[res].width)
    img = name_ribbon(img, i18n.texts(order.language)["special_for"], invitee.name)
    if res == "free":
        return to_bytes(credit_stamp(img, f"Made with love · {settings.brand_name}"), "JPEG", 88)
    if final.card_key == "main":
        img = add_qr(img, invites.invite_url(invitee), STYLES[card.style_key])
    return to_bytes(img, "JPEG", 92)


def main_final(order: Order) -> Asset | None:
    """The main card's final, unless its Indian-script text failed shaping QC."""
    final = next((a for a in order.live_assets("final") if a.card_key == "main"), None)
    if final is None or any(c["name"] == "script_shaping" and c["status"] == "fail" for c in (final.qc or {}).get("checks", [])):
        return None
    return final
