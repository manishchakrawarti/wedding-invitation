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

from app import seo, wording
from app.config import APP_DIR, settings
from app.templating import templates

log = logging.getLogger(__name__)
router = APIRouter()
ICONS = APP_DIR / "static" / "icons"
PUBLIC_PAGES = ["/", "/occasions", "/create", "/gallery", "/partners", "/order", "/terms", "/privacy", "/refund"]
UPDATED = date.today().isoformat()  # pages change with deploys, and the app restarts on every deploy


def indexnow_key() -> str:
    return hashlib.sha256(f"indexnow:{settings.base_url}".encode()).hexdigest()[:32]


def sitemap_paths() -> list[str]:
    return (PUBLIC_PAGES[:5] + [p.path for p in seo.pages().values()] + ["/wording"]
            + [p.path for p in wording.pages().values()] + PUBLIC_PAGES[5:])


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return ("User-agent: *\nDisallow: /admin\nDisallow: /o/\nDisallow: /i/\nDisallow: /e/\nDisallow: /webhooks/\n"
            f"Sitemap: {settings.base_url}/sitemap.xml\n")


@router.get("/sitemap.xml")
def sitemap():
    def entry(path: str) -> str:
        priority = ("1.0" if path == "/" else "0.9" if path.endswith(seo.SUFFIX) or path in ("/create", "/occasions")
                    else "0.8" if path.startswith("/wording") else "0.3")
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
    """The installable web app (and the Android app, which opens the site in a Trusted Web Activity)."""
    icons = [{"src": f"/static/icons/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any"} for n in (192, 512)]
    icons.append({"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"})
    return {
        "id": "/", "name": f"{settings.brand_name}: Invitation Card Maker", "short_name": settings.brand_name,
        "description": "Beautiful invitation cards for weddings, birthdays, pujas and every occasion, in Hindi and 9 Indian languages.",
        "start_url": "/?utm_source=app", "scope": "/", "display": "standalone", "orientation": "portrait", "lang": "en-IN",
        "background_color": "#7a1a2b", "theme_color": "#7a1a2b", "categories": ["lifestyle", "productivity", "photo"],
        "icons": icons,
        "shortcuts": [
            {"name": "Create an invitation", "short_name": "Create", "url": "/create?utm_source=app_shortcut",
             "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
            {"name": "Invitation messages", "short_name": "Messages", "url": "/wording?utm_source=app_shortcut",
             "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
            {"name": "Real invitations", "short_name": "Gallery", "url": "/gallery?utm_source=app_shortcut",
             "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
        ],
    }


@router.get("/.well-known/assetlinks.json")
def assetlinks():
    """Tells Android the Invite All app may show this site full screen (no browser bar). The fingerprints are of
    the app's signing keys: our upload key, and Google Play's app-signing key once the app is on Play."""
    prints = [f.strip().upper() for f in settings.android_sha256.split(",") if f.strip()]
    if not prints:
        return []
    return [{"relation": ["delegate_permission/common.handle_all_urls"],
             "target": {"namespace": "android_app", "package_name": settings.android_package, "sha256_cert_fingerprints": prints}}]


SERVICE_WORKER = """// Invite All service worker: an offline page, and quick start for the app's icons and styles.
const CACHE = 'ia-v1';
const OFFLINE = '/offline';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll([OFFLINE, '/static/icons/icon-192.png'])).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match(OFFLINE)));
  }
});
"""


@router.get("/sw.js")
def service_worker():
    return Response(SERVICE_WORKER, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/offline", response_class=HTMLResponse)
def offline(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})


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


@router.get("/wording", response_class=HTMLResponse)
def wording_index(request: Request):
    from app import events

    groups = [(c.name, [p for p in wording.pages().values() if p.category == key]) for key, c in events.CATEGORIES.items()]
    return templates.TemplateResponse(request, "wording.html", {"w": None, "groups": [g for g in groups if g[1]]})


@router.get("/wording/{slug}", response_class=HTMLResponse)
def wording_page(request: Request, slug: str):
    page = wording.pages().get(slug)
    if page is None:
        raise HTTPException(404)
    others = [p for p in wording.pages().values() if p.category == page.category and p.slug != slug][:8]
    return templates.TemplateResponse(request, "wording.html", {"w": page, "pages": others})


@router.get("/{slug}", response_class=HTMLResponse)
def landing(request: Request, slug: str):
    page = seo.pages().get(slug)
    if page is None:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "landing.html", {"p": page, "related": seo.related(page), "faqs": page.faqs()})
