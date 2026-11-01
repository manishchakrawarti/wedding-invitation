"""Instant card preview while someone types (homepage "try it" and the create form): the card drawn on
the style's sample background at half size, in about a tenth of a second, with nothing saved."""
from datetime import date
from functools import lru_cache
from types import SimpleNamespace

from app import events
from app.catalog import LANGUAGES, STYLES
from app.services.cards import event_card, main_card
from app.services.overlay import LAYOUT_PLAIN, compose_card, to_bytes
from app.utils import clean_time

WIDTH = 540
LIMITS = {"a": 60, "b": 60, "a_local": 60, "b_local": 60, "detail": 60, "venue": 80, "city": 40}


@lru_cache(maxsize=16)
def _background(style_key: str):
    from app.services.generation import offline_generator

    return offline_generator().generate("", STYLES[style_key], LAYOUT_PLAIN, [], seed=7).image


def clean(params: dict) -> dict:
    """Only known fields, trimmed, with safe defaults: the preview URL is public."""
    event = params.get("event", "") if params.get("event", "") in events.TYPES else ""
    t = events.TYPES.get(event)
    styles = t.styles if t else tuple(k for k, s in STYLES.items() if "wedding" in s.occasions)
    style = params.get("style", "") if params.get("style", "") in styles else styles[0]
    try:
        when = date.fromisoformat(params.get("date", ""))
    except ValueError:
        when = None
    out = {k: str(params.get(k, "")).strip()[:n] for k, n in LIMITS.items()}
    out.update(event=event, style=style, lang=params.get("lang") if params.get("lang") in LANGUAGES else "en",
               date=when.isoformat() if when else "", time=clean_time(params.get("time", "")),
               fmt="24h" if params.get("fmt") == "24h" else "12h")
    return out


@lru_cache(maxsize=256)
def _render(key: tuple) -> bytes:
    p = dict(key)
    t = events.TYPES.get(p["event"])
    if t:
        primary, secondary, detail = t.demo
        a, b = p["a"] or primary, p["b"] or (secondary if not p["a"] else "")
    else:
        a, b = p["a"] or "Ananya", p["b"] or "Arjun"
    local = p["lang"] != "en"
    order = SimpleNamespace(
        language=p["lang"], style=p["style"], package="instant", addons=[], event_type=p["event"] or "wedding",
        is_wedding=not t, bride_name=a, groom_name=b,
        bride_name_local=(p["a_local"] or a) if local else "", groom_name_local=(p["b_local"] or b) if local else "",
        bride_family="", groom_family="", occasion_detail=p["detail"] or (t.demo[2] if t and not p["a"] else ""),
        wedding_date=date.fromisoformat(p["date"]) if p["date"] else date(2026, 12, 12),
        venue_name=p["venue"] or "The Grand Banquet", venue_address="", city=p["city"] or ("Jaipur" if not p["venue"] else ""),
        functions=[{"key": p["event"] or "wedding", "time": p["time"] or "19:30"}], time_format=p["fmt"], event=None,
    )
    card = event_card(order) if t else main_card(order)
    img, _ = compose_card(_background(p["style"]), card.items, STYLES[card.style_key], LAYOUT_PLAIN, k=WIDTH / 1080)
    return to_bytes(img, "JPEG", 82)


def render(params: dict) -> bytes:
    return _render(tuple(sorted(clean(params).items())))
