from datetime import date
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from app import catalog, i18n
from app.config import APP_DIR, settings
from app.models import STATUS_LABELS, OrderStatus
from app.utils import inr, pretty_date, pretty_time

templates = Jinja2Templates(directory=APP_DIR / "templates")
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
    wa_link=lambda text="": f"https://wa.me/{settings.whatsapp_number}?text={quote(text)}",
)
