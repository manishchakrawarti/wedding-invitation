"""Decides which cards an order gets and what text goes on each one."""
from dataclasses import dataclass

from app import i18n
from app.catalog import ENGLISH_INVITE_LINE, FUNCTIONS, LANGUAGES, PACKAGES, card_style_for
from app.services.overlay import Divider, Line
from app.utils import pretty_date, pretty_time

MAIN_CEREMONIES = ("wedding", "nikah")
STYLE_HEADLINES_EN = {"muslim_nikah": "Nikah Invitation", "christian": "Holy Matrimony"}


@dataclass
class CardSpec:
    key: str  # "main" or a function key
    title: str
    style_key: str
    items: list
    with_photo: bool


def has_function_cards(order) -> bool:
    return PACKAGES[order.package].function_cards or "function_cards" in (order.addons or [])


def has_rsvp(order) -> bool:
    """Has an invite page (general link + RSVP)."""
    pkg = PACKAGES[order.package]
    return pkg.rsvp or pkg.event_page or "rsvp" in (order.addons or [])


def has_guest_console(order) -> bool:
    """Smart guest invites: personal links, tracking, headcounts (Premium or the add-on)."""
    return PACKAGES[order.package].rsvp or "rsvp" in (order.addons or [])


def _names(order) -> tuple[str, str]:
    local = order.language != "en"
    bride = order.bride_name_local if local and order.bride_name_local else order.bride_name
    groom = order.groom_name_local if local and order.groom_name_local else order.groom_name
    return bride.strip(), groom.strip()


def _function_label(order, key: str) -> str:
    return i18n.function_name(order.language, key, FUNCTIONS[key])


def main_card(order) -> CardSpec:
    lang = LANGUAGES[order.language]
    bride, groom = _names(order)
    headline = STYLE_HEADLINES_EN.get(order.style, lang.headline) if order.language == "en" else lang.headline
    ceremony = next((f for f in order.functions or [] if f["key"] in MAIN_CEREMONIES), None)

    items: list = [
        Line(headline, "headline", 46, "accent"),
        Divider(gap_before=10),
        Line(lang.invite_line or ENGLISH_INVITE_LINE, "invite", 34, "secondary", max_lines=3, gap_before=14),
        Line(bride, "names", 128, "primary", gap_before=26),
    ]
    t = i18n.texts(order.language)
    daughter_of = "Daughter of" if order.language == "en" else t["daughter_of"]
    son_of = "Son of" if order.language == "en" else t["son_of"]
    if order.bride_family:
        items.append(Line(f"{daughter_of} {order.bride_family}", "family", 28, gap_before=2))
    items.append(Line(lang.connector, "connector", 64, "accent", gap_before=6))
    items.append(Line(groom, "names", 128, "primary", gap_before=6))
    if order.groom_family:
        items.append(Line(f"{son_of} {order.groom_family}", "family", 28, gap_before=2))
    items += [Divider(gap_before=26), Line(pretty_date(order.wedding_date), "date", 38, "accent", gap_before=14)]
    if ceremony and ceremony.get("time"):
        items.append(Line(f"at {pretty_time(ceremony['time'])}", "detail", 32, gap_before=4))
    items.append(Line(order.venue_name, "detail", 36, "primary", max_lines=2, gap_before=16))
    address = ", ".join(p for p in (order.venue_address, order.city) if p)
    if address:
        items.append(Line(address, "small", 28, max_lines=2, gap_before=4))
    return CardSpec("main", "Main invitation", order.style, items, with_photo=True)


def function_card(order, fn: dict) -> CardSpec:
    bride, groom = _names(order)
    lang = LANGUAGES[order.language]
    key = fn["key"]
    items: list = [
        Line("Join us for the" if order.language == "en" else i18n.texts(order.language)["invited"], "invite", 34, gap_before=0),
        Line(_function_label(order, key), "title", 120, "primary", gap_before=10),
        Divider(gap_before=10),
        Line(f"{bride} {lang.connector} {groom}", "headline", 44, "accent", max_lines=2, gap_before=18),
        Line(pretty_date(fn.get("date") or order.wedding_date), "date", 38, "secondary", gap_before=30),
    ]
    if fn.get("time"):
        items.append(Line(pretty_time(fn["time"]), "detail", 34, gap_before=6))
    items.append(Line(fn.get("venue") or order.venue_name, "detail", 36, "primary", max_lines=2, gap_before=16))
    return CardSpec(key, FUNCTIONS[key], card_style_for(order.style, key), items, with_photo=False)


def cards_for_order(order) -> list[CardSpec]:
    cards = [main_card(order)]
    if has_function_cards(order):
        for fn in order.functions or []:
            if fn["key"] not in MAIN_CEREMONIES:
                cards.append(function_card(order, fn))
    return cards


def expected_texts(card: CardSpec) -> list[str]:
    return [i.text for i in card.items if isinstance(i, Line)]
