"""Save the Date: a teaser card sent weeks before the invitation, drawn on the same design as the main card.
Free for every invitation (the free size carries the small credit, so every share advertises the site)."""
import io

from PIL import Image

from app import i18n
from app.catalog import LANGUAGES, RESOLUTIONS, STYLES
from app.config import settings
from app.models import Order
from app.services import hires
from app.services.cards import _names
from app.services.overlay import CANVAS, LAYOUT_PLAIN, Divider, Line, compose_card, credit_stamp, to_bytes
from app.services.storage import storage
from app.utils import pretty_date


def items(order: Order) -> list:
    t = i18n.texts(order.language)
    if order.is_wedding:
        first, second = _names(order)
        connector = "&" if order.language == "en" else LANGUAGES[order.language].connector
    else:
        from app import events

        e = events.texts(order)
        first, second, connector = e["primary"], e["secondary"], "&"
    lines: list = [Line(t["save_date"], "headline", 64, "accent"), Divider(gap_before=16)]
    if not order.is_wedding:
        lines.append(Line(e["headline"], "detail", 42, "primary", gap_before=14))
    lines.append(Line(first, "names", 124, "primary", gap_before=24))
    if second:
        lines += [Line(connector, "connector", 60, "accent", gap_before=6), Line(second, "names", 124, "primary", gap_before=6)]
    lines += [Divider(gap_before=24), Line(pretty_date(order.wedding_date), "date", 52, "accent", gap_before=16)]
    if order.city:
        lines.append(Line(order.city, "detail", 38, "primary", gap_before=10))
    lines.append(Line(t["invite_follow"], "small", 30, gap_before=24))
    return lines


_cache: dict[tuple, bytes] = {}


def ready(order: Order) -> bool:
    return hires.main_final(order) is not None


def render(order: Order) -> bytes:
    """Full HD once a size is bought, else the free size with the credit. Kept in memory until the details change."""
    final = hires.main_final(order)
    if final is None:
        raise LookupError("no card yet")
    key = (order.id, final.id, str(order.updated_at), hires.personal_tier(order))
    if key not in _cache:
        if len(_cache) > 24:
            _cache.clear()
        _cache[key] = _render(order, final)
    return _cache[key]


def _render(order: Order, final) -> bytes:
    background = next(a for a in order.assets if a.kind == "background" and a.card_key == "main" and a.version == final.version)
    res = hires.personal_tier(order)
    bg = Image.open(io.BytesIO(storage.read(background.path)))
    img, _ = compose_card(bg, items(order), STYLES[order.style], LAYOUT_PLAIN, k=RESOLUTIONS[res].width / CANVAS[0])
    if res == "free":
        return to_bytes(credit_stamp(img, f"Made with love · {settings.brand_name}"), "JPEG", 88)
    return to_bytes(img, "JPEG", 92)
