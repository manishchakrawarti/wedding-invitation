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


def pretty_time(t: str | None) -> str:
    if not t:
        return ""
    return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
