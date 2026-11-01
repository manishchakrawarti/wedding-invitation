import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import APP_DIR, settings
from app.db import init_db
from app.routes import admin, public, rsvp, webhooks
from app.services import demo, maintenance, pipeline, telegram
from app.services.overlay import RAQM

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.run_pipeline_inline:
        recovered = pipeline.recover_stuck_orders()
        if recovered:
            log.info("re-queued %d unfinished order(s)", recovered)
        maintenance.start_daily_cleanup()
        threading.Thread(target=demo.ensure_demo, name="demo", daemon=True).start()
        if settings.telegram_enabled:
            telegram.setup()
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


app = FastAPI(title=settings.brand_name, lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(public.router)
app.include_router(rsvp.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}
