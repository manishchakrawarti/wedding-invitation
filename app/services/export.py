"""E-invite export: the whole invitation as a PDF booklet or one long image (for WhatsApp).

A print-designed page (templates/invite_print.html) is rendered by headless Chrome/Chromium.
Browsers shape Hindi and other Indian scripts correctly everywhere, and every font and image
is embedded as a data URI, so rendering needs no network access. Results are cached in storage.
"""
import base64
import hashlib
import io
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

import qrcode

from app import events, i18n
from app.catalog import LANGUAGES, STYLES
from app.config import settings
from app.models import Order
from app.services import gifts, invites
from app.services.cards import cards_for_order
from app.services.overlay import CANVAS, FONT_DIR, SCRIPT_FONTS
from app.services.storage import storage

PAGE_W, PAGE_H = CANVAS
SCRIPT_OF_LANG = {
    "hi": "devanagari", "mr": "devanagari", "bn": "bengali", "gu": "gujarati", "pa": "gurmukhi",
    "ta": "tamil", "te": "telugu", "kn": "kannada", "ml": "malayalam",
}


class ExportUnavailable(RuntimeError):
    pass


def chrome_binary() -> str | None:
    candidates = [settings.chrome_path] if settings.chrome_path else []
    if platform.system() == "Windows":
        candidates += [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    candidates += [shutil.which(n) or "" for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")]
    return next((c for c in candidates if c and Path(c).exists()), None)


@lru_cache(maxsize=16)
def _font_uri(filename: str) -> str:
    data = (FONT_DIR / filename).read_bytes()
    return "data:font/ttf;base64," + base64.b64encode(data).decode()


def _uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _qr_uri(url: str) -> str:
    buf = io.BytesIO()
    qrcode.make(url, box_size=12, border=2).save(buf, "PNG")
    return _uri(buf.getvalue(), "image/png")


def build_html(order: Order, tier: str = "1080", pages_range: tuple[int, int] | None = None) -> tuple[str, int]:
    """The print page and its number of pages.

    tier sets the card images inside (free = 720 with a credit and no RSVP QR, since the
    invite page only goes live once a paid size is bought). pages_range (first, last) renders only those pages.
    """
    from app.services import hires
    from app.templating import templates

    finals = {
        a.card_key: a for a in order.live_assets("final")
        if not any(c["name"] == "script_shaping" and c["status"] == "fail" for c in (a.qc or {}).get("checks", []))
    }
    _, mime = hires.file_info(tier)
    card_pages = [
        {"title": c.title, "src": _uri(hires.render(order, finals[c.key], tier), mime)}
        for c in cards_for_order(order) if c.key in finals
    ]
    schedule = invites.schedule(order)
    script = SCRIPT_OF_LANG.get(order.language)
    fonts = {
        "GreatVibes": _font_uri("GreatVibes-Regular.ttf"),
        "Cinzel": _font_uri("Cinzel.ttf"),
        "Cormorant": _font_uri("CormorantGaramond.ttf"),
    }
    if script:
        fonts["LocalScript"] = _font_uri(SCRIPT_FONTS[script])
    photos = {}
    for role, asset in invites.portraits(order).items():
        from PIL import Image

        img = Image.open(io.BytesIO(storage.read(asset.path))).convert("RGB")
        img.thumbnail((900, 900))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        photos[role] = _uri(buf.getvalue(), "image/jpeg")
    gift = gifts.info(order)
    if gift:
        found = gifts.qr_bytes(order)
        gift = {**gift, "qr": _uri(*found) if found else ""}
    pages = 1 + len(card_pages) + (1 if schedule else 0) + 1 + (1 if gift else 0)
    free = tier == "free"
    rsvp_url = f"{settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug and not free else ""
    html = templates.get_template("invite_print.html").render(
        o=order, st=STYLES[order.style], t=i18n.texts(order.language), lang=LANGUAGES[order.language],
        local=order.language != "en", fonts=fonts, card_pages=card_pages, schedule=schedule, ev=order.event,
        qr=_qr_uri(rsvp_url) if rsvp_url else "", rsvp_url=rsvp_url, invocation=i18n.INVOCATIONS.get(order.language, ""),
        W=PAGE_W, H=PAGE_H, settings=settings, credit=f"Made with love · {settings.brand_name}" if free else "",
        pages_range=pages_range, photos=photos, occ=None if order.is_wedding else events.texts(order), gift=gift,
    )
    return html, pages


MAX_SHOT_HEIGHT = 15000  # Chrome can't screenshot taller than ~16k px in one go


def _chrome(chrome: str, tmp: str, html: str, out: Path, extra: list[str]) -> None:
    page = Path(tmp, f"{out.stem}.html")
    page.write_text(html, encoding="utf-8")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars",
           f"--user-data-dir={Path(tmp, 'profile')}", "--virtual-time-budget=5000", *extra, page.as_uri()]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180, env={**os.environ})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExportUnavailable(f"Rendering failed: {exc}") from exc
    if not out.exists() or out.stat().st_size == 0:
        raise ExportUnavailable(f"Rendering failed: {proc.stderr.decode(errors='ignore')[-300:]}")


# Chromium + big images are the heaviest thing the app does; on small/free servers render one at a time.
_render_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_renders))


def render(order: Order, fmt: str, tier: str = "1080") -> bytes:
    with _render_slots:
        return _render(order, fmt, tier)


def _render(order: Order, fmt: str, tier: str = "1080") -> bytes:
    """fmt 'pdf': one page per section. fmt 'image': all pages stacked into one tall JPEG
    whose width matches the tier (720 / 1080 / 2048 / 3840 px)."""
    from PIL import Image

    from app.catalog import RESOLUTIONS

    html, pages = build_html(order, tier)
    digest = hashlib.sha1(html.encode()).hexdigest()[:12]
    ext = "pdf" if fmt == "pdf" else "jpg"
    key = f"orders/{order.public_id}/einvite_{tier}_{digest}.{ext}"
    if storage.exists(key):
        return storage.read(key)
    chrome = chrome_binary()
    if not chrome:
        raise ExportUnavailable("Chrome/Chromium is not installed on the server")
    k = RESOLUTIONS[tier].width / PAGE_W
    with tempfile.TemporaryDirectory() as tmp:
        if fmt == "pdf":
            out = Path(tmp, "out.pdf")
            _chrome(chrome, tmp, html, out, ["--no-pdf-header-footer", "--print-to-pdf-no-header", f"--print-to-pdf={out}"])
            data = out.read_bytes()
        else:
            scale = [f"--force-device-scale-factor={k:.4f}"]
            if PAGE_H * pages * k <= MAX_SHOT_HEIGHT:  # one screenshot of the whole stack
                out = Path(tmp, "all.png")
                _chrome(chrome, tmp, html, out, [*scale, f"--window-size={PAGE_W},{PAGE_H * pages}", f"--screenshot={out}"])
                img = Image.open(out).convert("RGB")
            else:  # 2K/4K: render in chunks of pages that fit one screenshot, then stitch
                per_shot = max(1, int(MAX_SHOT_HEIGHT // (PAGE_H * k)))
                shots = []
                for first in range(1, pages + 1, per_shot):
                    last = min(first + per_shot - 1, pages)
                    chunk_html, _ = build_html(order, tier, pages_range=(first, last))
                    out = Path(tmp, f"p{first}.png")
                    _chrome(chrome, tmp, chunk_html, out,
                            [*scale, f"--window-size={PAGE_W},{PAGE_H * (last - first + 1)}", f"--screenshot={out}"])
                    shots.append(Image.open(out).convert("RGB"))
                img = Image.new("RGB", (shots[0].width, sum(s.height for s in shots)))
                y = 0
                for shot in shots:
                    img.paste(shot, (0, y))
                    y += shot.height
            target = (RESOLUTIONS[tier].width, RESOLUTIONS[tier].height * pages)
            if img.size != target:  # device-scale rounding: snap to the exact advertised size
                img = img.resize(target, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85 if tier == "free" else 92, optimize=True)
            data = buf.getvalue()
    storage.save(key, data)
    return data
