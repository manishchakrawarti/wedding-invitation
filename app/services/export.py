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
from functools import lru_cache
from pathlib import Path

import qrcode

from app import i18n
from app.catalog import LANGUAGES, STYLES
from app.config import settings
from app.models import Order
from app.services import invites
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


def build_html(order: Order) -> tuple[str, int]:
    """The print page and its number of pages."""
    from app.templating import templates

    finals = {
        a.card_key: a for a in order.live_assets("final")
        if not any(c["name"] == "script_shaping" and c["status"] == "fail" for c in (a.qc or {}).get("checks", []))
    }
    card_pages = [
        {"title": c.title, "src": _uri(storage.read(finals[c.key].path), finals[c.key].content_type)}
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
    pages = 1 + len(card_pages) + (1 if schedule else 0) + 1
    rsvp_url = f"{settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug else ""
    html = templates.get_template("invite_print.html").render(
        o=order, st=STYLES[order.style], t=i18n.texts(order.language), lang=LANGUAGES[order.language],
        local=order.language != "en", fonts=fonts, card_pages=card_pages, schedule=schedule, ev=order.event,
        qr=_qr_uri(rsvp_url) if rsvp_url else "", rsvp_url=rsvp_url, invocation=i18n.INVOCATIONS.get(order.language, ""),
        W=PAGE_W, H=PAGE_H, settings=settings,
    )
    return html, pages


def render(order: Order, fmt: str) -> bytes:
    """fmt: 'pdf' (one page per section) or 'png' (all pages stacked into one tall image)."""
    html, pages = build_html(order)
    digest = hashlib.sha1(html.encode()).hexdigest()[:12]
    key = f"orders/{order.public_id}/einvite_{digest}.{fmt}"
    if storage.exists(key):
        return storage.read(key)
    chrome = chrome_binary()
    if not chrome:
        raise ExportUnavailable("Chrome/Chromium is not installed on the server")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp, "invite.html")
        page.write_text(html, encoding="utf-8")
        out = Path(tmp, f"out.{fmt}")
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
               f"--user-data-dir={Path(tmp, 'profile')}", "--virtual-time-budget=5000", "--force-device-scale-factor=1"]
        if fmt == "pdf":
            cmd += ["--no-pdf-header-footer", "--print-to-pdf-no-header", f"--print-to-pdf={out}"]
        else:
            cmd += [f"--window-size={PAGE_W},{PAGE_H * pages}", f"--screenshot={out}"]
        cmd.append(page.as_uri())
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120, env={**os.environ})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExportUnavailable(f"Rendering failed: {exc}") from exc
        if not out.exists() or out.stat().st_size == 0:
            raise ExportUnavailable(f"Rendering failed: {proc.stderr.decode(errors='ignore')[-300:]}")
        data = out.read_bytes()
    storage.save(key, data)
    return data
