import hashlib
from datetime import date
from urllib.parse import quote, urlencode

from fastapi.templating import Jinja2Templates

from app import catalog, i18n, seo, ui_text, wording
from app.config import APP_DIR, settings
from app.models import STATUS_LABELS, OrderStatus
from app.services import cards as _cards, payments as _payments, telegram, video as _video
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
    video_state=lambda o: _video.state(o),
    video_allowed=lambda o: _video.allowed(o),
    upi_link=lambda p: _payments.upi_pay_link(p),
    family_line=_cards.family_line,
    degree_of=_cards.degree_of,
    wording=wording,
    wa_link=lambda text="": f"https://wa.me/{settings.whatsapp_number}?text={quote(text)}",
    ui_lang=lambda: ui_text.lang(),
    ui_switch=lambda request: (
        ("English", f"{request.url.path}?{urlencode({**dict(request.query_params), 'ui': 'en'})}") if ui_text.lang() == "hi"
        else ("हिन्दी", f"{request.url.path}?{urlencode({**dict(request.query_params), 'ui': 'hi'})}")),
)
