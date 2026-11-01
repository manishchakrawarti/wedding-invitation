import hashlib
from datetime import date
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from app import catalog, i18n, seo
from app.config import APP_DIR, settings
from app.models import STATUS_LABELS, OrderStatus
from app.services import telegram
from app.utils import inr, pretty_date, pretty_time

templates = Jinja2Templates(directory=APP_DIR / "templates")
# changes whenever style.css does, so browsers fetch the new stylesheet after a deploy
CSS_VERSION = hashlib.md5((APP_DIR / "static" / "css" / "style.css").read_bytes()).hexdigest()[:8]
templates.env.globals.update(
    settings=settings,
    catalog=catalog,
    i18n=i18n,
    inr=inr,
    pretty_date=pretty_date,
    pretty_time=pretty_time,
    OrderStatus=OrderStatus,
    STATUS_LABELS=STATUS_LABELS,
    current_year=date.today().year,
    css_version=CSS_VERSION,
    telegram=telegram,
    seo=seo,
    wa_link=lambda text="": f"https://wa.me/{settings.whatsapp_number}?text={quote(text)}",
)
