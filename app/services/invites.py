"""Smart guest invites: personal links, WhatsApp messages, calendar files and family stats."""
import re
import secrets
from datetime import date, datetime, timedelta
from urllib.parse import quote, quote_plus

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import i18n
from app.catalog import FUNCTIONS
from app.config import settings
from app.models import EventDetails, Invitee, Order
from app.utils import normalize_phone, pretty_date, pretty_time

FUNCTION_ICONS = {
    "engagement": "💍", "tilak": "🪔", "haldi": "💛", "mehndi": "🌿",
    "sangeet": "🎶", "wedding": "🔥", "nikah": "🌙", "reception": "🥂",
}
FOOD_CHOICES = {"veg": "Vegetarian", "jain": "Jain", "no-onion-garlic": "No onion / garlic", "non-veg": "Non-vegetarian"}


def event_details(db: Session, order: Order) -> EventDetails:
    if order.event is None:
        order.event = EventDetails(order_id=order.id, dress_codes={})
        db.add(order.event)
        db.flush()
    return order.event


PORTRAIT_ROLES = {"bride": "Bride's photo", "groom": "Groom's photo", "family": "Family photo"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def clean_photo(data: bytes) -> bytes:
    """Fix rotation, downscale and re-encode. This also strips EXIF metadata, including GPS location."""
    import io

    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def portraits(order: Order) -> dict:
    """Latest photo per role (bride / groom / family) shown on the invitation."""
    found = {}
    for a in sorted(order.live_assets("portrait"), key=lambda a: a.id):
        found[a.card_key] = a
    return found


def save_portrait(db: Session, order: Order, role: str, data: bytes, enhance: bool = True,
                  vibrant: bool = False, meta: dict | None = None) -> None:
    """Store a photo for a role (replacing any previous one): the original is kept, and the
    version shown on the invitation is face-framed and studio-finished unless enhance is off."""
    from app.models import Asset, utcnow
    from app.services import photo_enhance
    from app.services.storage import storage

    for old in [*order.live_assets("portrait"), *order.live_assets("portrait_raw")]:
        if old.card_key == role:
            storage.delete(old.path)
            old.deleted_at = utcnow()
    stem = f"orders/{order.public_id}/portraits/{role}_{secrets.token_hex(4)}"
    original = clean_photo(data)
    db.add(Asset(order_id=order.id, kind="portrait_raw", card_key=role, path=storage.save(f"{stem}_original.jpg", original),
                 content_type="image/jpeg"))
    shown, info = photo_enhance.enhance(original, role, vibrant=vibrant) if enhance else (original, {})
    db.add(Asset(order_id=order.id, kind="portrait", card_key=role, path=storage.save(f"{stem}.jpg", shown),
                 content_type="image/jpeg", meta={"enhanced": enhance, **info, **(meta or {})}))


async def read_portrait_uploads(form, errors: list[str], kept: dict[str, bytes] | None = None) -> dict[str, bytes]:
    """Validate the bride/groom/family photo fields of a submitted form. kept: photos already
    validated on an earlier try of the same form (see services/stash.py), used where no new file was chosen."""
    from PIL import UnidentifiedImageError

    photos = {}
    for role, label in PORTRAIT_ROLES.items():
        upload = form.get(f"{role}_photo")
        if not getattr(upload, "filename", ""):
            if kept and kept.get(role):
                photos[role] = kept[role]
            continue
        data = await upload.read()
        if len(data) > MAX_PHOTO_BYTES:
            errors.append(f"{label} is larger than 10 MB.")
            continue
        try:
            clean_photo(data)
        except (UnidentifiedImageError, OSError):
            errors.append(f"{label} must be a JPG, PNG or WebP image (iPhone HEIC: please export as JPG).")
            continue
        photos[role] = data
    if photos and not form.get("photo_consent"):
        errors.append("Please confirm you have permission to use these photos on the invitation.")
    return photos


def _event_icon(key: str) -> str:
    from app.events import TYPES

    return TYPES[key].icon if key in TYPES else "✨"


def place_for(order: Order, fn: dict) -> str:
    if fn.get("venue"):
        return f"{fn['venue']}, {order.city}" if order.city else fn["venue"]
    return ", ".join(p for p in (order.venue_name, order.venue_address, order.city) if p)


def map_link(place: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(place)}"


def map_embed(place: str) -> str:
    return f"https://www.google.com/maps?q={quote_plus(place)}&output=embed"


def schedule(order: Order, only: list[str] | None = None) -> list[dict]:
    """The order's functions in date order, optionally limited to the ones a guest is invited to."""
    dress = (order.event.dress_codes if order.event else None) or {}
    items = []
    for fn in sorted(order.functions or [], key=lambda f: (f.get("date") or "", f.get("time") or "")):
        if only and fn["key"] not in only:
            continue
        place = place_for(order, fn)
        when = fn.get("date") or order.wedding_date.isoformat()
        items.append({
            **fn,
            "date": when,
            "label": fn.get("label") or FUNCTIONS.get(fn["key"], fn["key"]),
            "label_local": (fn.get("label_hi", "") if order.language == "hi" else "") if fn.get("label")
            else (i18n.function_name(order.language, fn["key"], "") if order.language != "en" else ""),
            "icon": FUNCTION_ICONS.get(fn["key"]) or _event_icon(fn["key"]),
            "place": place,
            "map": map_link(place),
            "dress": dress.get(fn["key"], ""),
            "pretty_date": pretty_date(when),
            "pretty_time": pretty_time(fn.get("time")),
        })
    return items


def main_moment(order: Order) -> str:
    """ISO datetime of the main ceremony, for the countdown."""
    ceremony = next((f for f in order.functions or [] if f["key"] in ("wedding", "nikah")), None)
    day = (ceremony or {}).get("date") or order.wedding_date.isoformat()
    time = (ceremony or {}).get("time") or "18:00"
    return f"{day}T{time}:00"


def invite_url(invitee: Invitee) -> str:
    return f"{settings.base_url}/i/{invitee.code}"


def whatsapp_text(order: Order, invitee: Invitee) -> str:
    """Personal WhatsApp message in the card's language."""
    t = i18n.texts(order.language)
    local = order.language != "en"
    bride = order.bride_name_local if local and order.bride_name_local else order.bride_name
    groom = order.groom_name_local if local and order.groom_name_local else order.groom_name
    hosts = order.event.hosts if order.event and order.event.hosts else t["our_families"]
    if getattr(order, "is_wedding", True):
        body = t["invite_para"].format(hosts=hosts, bride=bride, groom=groom)
    else:
        from app import events

        body = events.texts(order)["para"]
    return (
        f"🙏 {t['dear'].format(name=invitee.name)},\n\n{body}\n"
        f"📅 {pretty_date(order.wedding_date)}\n\n"
        f"{t['your_invitation']} 💌 {invite_url(invitee)}"
    )


def whatsapp_link(order: Order, invitee: Invitee) -> str:
    phone = normalize_phone(invitee.phone) if invitee.phone else ""
    return f"https://wa.me/{phone}?text={quote(whatsapp_text(order, invitee))}"


def new_code(db: Session) -> str:
    while True:
        code = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
        if not db.scalar(select(Invitee.id).where(Invitee.code == code)):
            return code


def _match_function(word: str, available: list[str]) -> str | None:
    word = word.strip().lower()
    for key in available:
        if word and (word == key or FUNCTIONS[key].lower().startswith(word)):
            return key
    return None


def parse_guest_lines(text: str, available: list[str], default_functions: list[str]) -> list[dict]:
    """One guest per line: `Name, phone, functions…, side`. Only the name is required.
    Functions can be written like 'haldi sangeet' or 'reception'; 'bride'/'groom' sets the side."""
    guests = []
    for raw in text.splitlines():
        parts = [p.strip() for p in raw.split(",")]
        if not parts or not parts[0]:
            continue
        name, phone, functions, side = parts[0][:120], "", [], ""
        for part in parts[1:]:
            if re.fullmatch(r"[+\d][\d\s-]{6,}", part):
                phone = normalize_phone(part)
                continue
            for word in re.split(r"[\s+/&]+", part):
                if word.lower() in ("bride", "groom", "ladkiwale", "ladkewale"):
                    side = "bride" if word.lower() in ("bride", "ladkiwale") else "groom"
                elif (key := _match_function(word, available)) and key not in functions:
                    functions.append(key)
        guests.append({"name": name, "phone": phone, "functions": functions or list(default_functions), "side": side})
    return guests


def stats(order: Order) -> dict:
    inv = order.invitees
    replied = [i for i in inv if i.attending]
    coming = [i for i in replied if i.attending in ("yes", "maybe")]
    per_function = {}
    for fn in schedule(order):
        key = fn["key"]
        per_function[key] = {
            "label": fn["label"], "icon": fn["icon"],
            "invited": sum(1 for i in inv if not i.functions or key in i.functions),
            "headcount": sum(i.headcount for i in coming if key in (i.attending_functions or [])),
        }
    food = {k: sum(i.headcount for i in coming if i.food == k) for k in FOOD_CHOICES}
    walk_ins = sum(g.headcount for g in order.guests if g.attending != "no")
    return {
        "invited": len(inv),
        "sent": sum(1 for i in inv if i.sent_at),
        "opened": sum(1 for i in inv if i.opened_at),
        "replied": len(replied),
        "yes_people": sum(i.headcount for i in replied if i.attending == "yes"),
        "maybe_people": sum(i.headcount for i in replied if i.attending == "maybe"),
        "declined": sum(1 for i in replied if i.attending == "no"),
        "pickups": sum(1 for i in coming if i.needs_pickup),
        "per_function": per_function,
        "food": food,
        "walk_ins": walk_ins,
    }


def ics(order: Order, fn: dict) -> str:
    start = datetime.fromisoformat(f"{fn['date']}T{fn.get('time') or '18:00'}")
    end = start + timedelta(hours=4)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    title = f"{fn['label']}: {order.display_names}"

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{settings.brand_name}//Invite//EN", "BEGIN:VEVENT",
        f"UID:{order.public_id}-{fn['key']}@{settings.brand_name.replace(' ', '').lower()}",
        f"DTSTAMP:{stamp}", f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}",
        f"SUMMARY:{esc(title)}", f"LOCATION:{esc(fn['place'])}",
        "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", f"DESCRIPTION:{esc(title)} tomorrow", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", "",
    ])


def days_until(order: Order) -> int:
    return (order.wedding_date - date.today()).days
