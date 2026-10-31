import re
import secrets
from datetime import date, datetime

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion when read aloud


def short_code(n: int = 4) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def new_token() -> str:
    return secrets.token_urlsafe(24)


def inr(paise: int | float, with_symbol: bool = True) -> str:
    """Format paise as Indian rupees with lakh grouping: 149999900 -> ₹14,99,999."""
    rupees = int(round(paise / 100))
    sign = "-" if rupees < 0 else ""
    s = str(abs(rupees))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"{sign}{'₹' if with_symbol else ''}{s}"


def normalize_phone(raw: str) -> str:
    """Digits only, with India's 91 prefix added to bare 10-digit mobile numbers."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def pretty_date(d: date | str | None) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%A, %d %B %Y").replace(" 0", " ")


def clean_time(raw: str | None) -> str:
    """A form time as 24-hour 'HH:MM', or '' if empty or invalid. Accepts '19:30', '7:30', '7:30 PM', '7 pm'."""
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp]\.?[Mm]\.?)?\s*", raw or "")
    if not m:
        return ""
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()[:1]
    if ampm:
        if not 1 <= hour <= 12:
            return ""
        hour = hour % 12 + (12 if ampm == "p" else 0)
    if hour > 23 or minute > 59 or (not ampm and m.group(2) is None):
        return ""
    return f"{hour:02d}:{minute:02d}"


def pretty_time(t: str | None, fmt: str = "12h") -> str:
    """'19:30' -> '7:30 PM' (fmt '12h') or '19:30' (fmt '24h')."""
    if not t:
        return ""
    when = datetime.strptime(t, "%H:%M")
    return when.strftime("%H:%M") if fmt == "24h" else when.strftime("%I:%M %p").lstrip("0")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
