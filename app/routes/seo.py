"""Search engines: robots.txt, sitemap, icons, IndexNow, and the occasion landing pages (app/seo.py).

Included last in app/main.py: the landing pages answer single-segment paths like /griha-pravesh-invitation-card,
so every other route must get the first chance to match."""
import hashlib
import json
import logging
import threading
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from app import seo
from app.config import APP_DIR, settings
from app.templating import templates

log = logging.getLogger(__name__)
router = APIRouter()
ICONS = APP_DIR / "static" / "icons"
PUBLIC_PAGES = ["/", "/occasions", "/create", "/order", "/terms", "/privacy", "/refund"]
UPDATED = date.today().isoformat()  # pages change with deploys, and the app restarts on every deploy


def indexnow_key() -> str:
    return hashlib.sha256(f"indexnow:{settings.base_url}".encode()).hexdigest()[:32]


def sitemap_paths() -> list[str]:
    return PUBLIC_PAGES[:3] + [p.path for p in seo.pages().values()] + PUBLIC_PAGES[3:]


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return ("User-agent: *\nDisallow: /admin\nDisallow: /o/\nDisallow: /i/\nDisallow: /e/\nDisallow: /webhooks/\n"
            f"Sitemap: {settings.base_url}/sitemap.xml\n")


@router.get("/sitemap.xml")
def sitemap():
    def entry(path: str) -> str:
        priority = "1.0" if path == "/" else "0.9" if path.endswith(seo.SUFFIX) or path in ("/create", "/occasions") else "0.3"
        return f"<url><loc>{settings.base_url}{path}</loc><lastmod>{UPDATED}</lastmod><priority>{priority}</priority></url>"

    urls = "".join(entry(p) for p in sitemap_paths())
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                    media_type="application/xml")


@router.get("/favicon.ico")
def favicon():
    return FileResponse(ICONS / "favicon.ico", media_type="image/x-icon", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/apple-touch-icon.png")
def apple_touch_icon():
    return FileResponse(ICONS / "apple-touch-icon.png", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/site.webmanifest")
def manifest():
    return {"name": settings.brand_name, "short_name": settings.brand_name, "start_url": "/", "display": "standalone",
            "background_color": "#fff8ec", "theme_color": "#7a1a2b",
            "icons": [{"src": f"/static/icons/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (192, 512)]}


@router.get("/indexnow-key.txt", response_class=PlainTextResponse)
def indexnow_key_file() -> str:
    return indexnow_key()


def ping_indexnow() -> None:
    """Tell Bing (and DuckDuckGo, Yahoo, Yandex… which use it) about our pages, once per change of the page list.
    Free, no account needed. Google doesn't take IndexNow: it reads the sitemap from Search Console."""
    if not settings.base_url.startswith("https://") or "localhost" in settings.base_url:
        return
    urls = [settings.base_url + p for p in sitemap_paths()]
    stamp = settings.data_dir / "indexnow.sent"
    digest = hashlib.sha256(json.dumps(urls).encode()).hexdigest()
    try:
        if stamp.exists() and stamp.read_text() == digest:
            return
        host = settings.base_url.split("//", 1)[1].split("/")[0]
        resp = httpx.post("https://api.indexnow.org/indexnow", timeout=20, json={
            "host": host, "key": indexnow_key(), "keyLocation": f"{settings.base_url}/indexnow-key.txt", "urlList": urls})
        if resp.status_code in (200, 202):
            stamp.write_text(digest)
        log.info("IndexNow: %s for %d URLs", resp.status_code, len(urls))
    except Exception:  # noqa: BLE001 — only a nudge; the sitemap still works
        log.warning("IndexNow ping failed", exc_info=True)


def start_indexnow() -> None:
    threading.Thread(target=ping_indexnow, name="indexnow", daemon=True).start()


@router.get("/{slug}", response_class=HTMLResponse)
def landing(request: Request, slug: str):
    page = seo.pages().get(slug)
    if page is None:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "landing.html", {"p": page, "related": seo.related(page), "faqs": page.faqs()})
