import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app import ui_text
from app.config import APP_DIR, settings
from app.db import init_db
from app.routes import admin, public, rsvp, seo, webhooks
from app.services import demo, maintenance, pipeline, stats, telegram
from app.services.overlay import RAQM

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def _demos_then_sample_video() -> None:
    from app.services import video

    demo.ensure_demo()
    video.ensure_sample()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.run_pipeline_inline:
        recovered = pipeline.recover_stuck_orders()
        if recovered:
            log.info("re-queued %d unfinished order(s)", recovered)
        maintenance.start_daily_cleanup()
        threading.Thread(target=_demos_then_sample_video, name="demo", daemon=True).start()
        if settings.telegram_enabled:
            telegram.setup()
        seo.start_indexnow()
        stats.start_flusher()
    if settings.admin_password == "change-me":
        log.warning("ADMIN_PASSWORD is the default — set it in .env before going live")
    if not RAQM:
        log.warning("libraqm/FriBiDi not available: Indian-script text cannot be shaped (English works). Use Docker for Hindi etc.")
    log.info(
        "payments=%s generator=%s telegram=%s whatsapp=%s email=%s",
        "razorpay" if settings.payments_live else "SIMULATED",
        "gemini" if settings.gemini_enabled else "offline",
        "on" if settings.telegram_enabled else "log-only",
        "on" if settings.whatsapp_enabled else "log-only",
        "on" if settings.email_enabled else "log-only",
    )
    yield
    stats.flush()


app = FastAPI(title=settings.brand_name, lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(public.router)
app.include_router(rsvp.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.middleware("http")
async def site_language(request: Request, call_next):
    """Hindi or English website (app/ui_text.py): ?ui=hi|en switches and is remembered in a cookie."""
    chosen = request.query_params.get("ui", "")
    ui_text.set_lang(chosen or request.cookies.get(ui_text.COOKIE, "en"))
    response = await call_next(request)
    path = request.url.path
    if chosen in ("hi", "en"):
        response.set_cookie(ui_text.COOKIE, chosen, max_age=365 * 86400, samesite="lax", secure=settings.base_url.startswith("https://"))
    if (ui_text.lang() == "hi" and not path.startswith(ui_text.SKIP_PREFIXES)
            and response.headers.get("content-type", "").startswith("text/html")):
        body = b"".join([chunk async for chunk in response.body_iterator])
        translated = ui_text.translate_html(body.decode("utf-8")).encode("utf-8")
        page = Response(translated, status_code=response.status_code)
        # raw headers keep every Set-Cookie (a dict would keep only the last)
        page.raw_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"content-length"] + [
            (b"content-length", str(len(translated)).encode())]
        response = page
    return response


@app.middleware("http")
async def visitor_stats(request: Request, call_next):
    """Count page views and new visitors for the admin stats page (services/stats.py)."""
    response = await call_next(request)
    path = request.url.path
    if (request.method == "GET" and response.status_code == 200 and not path.startswith(("/admin", "/static"))
            and response.headers.get("content-type", "").startswith("text/html")):
        new = stats.VISITOR_COOKIE not in request.cookies
        stats.track(path, request.headers.get("user-agent", ""), request.headers.get("referer", ""),
                    request.query_params.get("utm_source", ""), new)
        if new:
            response.set_cookie(stats.VISITOR_COOKIE, "1", max_age=12 * 3600, httponly=True, samesite="lax",
                                secure=settings.base_url.startswith("https://"))
    return response


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


app.include_router(seo.router)  # keep last: its landing pages match /<anything>
