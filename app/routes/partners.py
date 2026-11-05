"""Partner programme pages: /partners (join), /partners/{token} (their dashboard), /p/{code} (their share link)."""
import io
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Order, Partner
from app.services import invites, notify, partners
from app.templating import templates

router = APIRouter()


def _partner(token: str, db: Session) -> Partner:
    partner = db.scalar(select(Partner).where(Partner.token == token)) if len(token) >= 20 else None
    if partner is None:
        raise HTTPException(404)
    return partner


@router.get("/partners", response_class=HTMLResponse)
def partners_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "partners.html", {
        "businesses": partners.BUSINESSES, "error": error, "percent": settings.partner_commission_percent})


@router.post("/partners")
async def partner_signup(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    def f(key: str, limit: int = 120) -> str:
        return str(form.get(key) or "").strip()[:limit]

    if f("website"):  # honeypot: people never see this field
        return RedirectResponse("/partners", status_code=303)
    phone = invites.clean_phone(f("phone", 20))
    error = "Please enter your name." if not f("name") else "Please enter your mobile number." if not phone else ""
    if error:
        return RedirectResponse(f"/partners?error={quote(error)}#join", status_code=303)
    existing = db.scalar(select(Partner).where(Partner.phone == phone))
    if existing:  # signing up again from the same number opens the same dashboard
        return RedirectResponse(f"/partners/{existing.token}", status_code=303)
    partner = Partner(code=partners.new_code(db, f("name")), token=secrets.token_urlsafe(24), name=f("name"),
                      business=f("business") if f("business") in partners.BUSINESSES else "other", city=f("city", 80),
                      phone=phone, upi_id=f("upi_id", 100))
    db.add(partner)
    db.commit()
    notify.alert_owner(db, f"🤝 New partner: {partner.name} ({partners.BUSINESSES[partner.business]}, "
                           f"{partner.city or 'city not given'}) {invites.pretty_phone(phone)} · code {partner.code}")
    return RedirectResponse(f"/partners/{partner.token}?new=1", status_code=303)


@router.get("/partners/{token}", response_class=HTMLResponse)
def partner_dashboard(request: Request, token: str, db: Session = Depends(get_db)):
    partner = _partner(token, db)
    recent = db.scalars(select(Order).where(Order.partner_code == partner.code).order_by(Order.id.desc()).limit(20)).all()
    return templates.TemplateResponse(request, "partner_dashboard.html", {
        "p": partner, "s": partners.summary(db, partner), "link": partners.link(partner), "recent": recent,
        "share": partners.share_text(partner), "percent": settings.partner_commission_percent,
        "business": partners.BUSINESSES.get(partner.business, "")})


@router.post("/partners/{token}/upi")
async def partner_upi(request: Request, token: str, db: Session = Depends(get_db)):
    partner = _partner(token, db)
    partner.upi_id = str((await request.form()).get("upi_id") or "").strip()[:100]
    db.commit()
    return RedirectResponse(f"/partners/{token}?saved=1", status_code=303)


@router.get("/partners/{token}/qr.png")
def partner_qr(token: str, db: Session = Depends(get_db)):
    """A QR of their link to print on a counter card or visiting card."""
    import qrcode

    buf = io.BytesIO()
    qrcode.make(partners.link(_partner(token, db)), box_size=10, border=2).save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@router.get("/p/{code}")
def partner_link(code: str, db: Session = Depends(get_db)):
    """A partner's share link: remember them for 60 days, then open the site."""
    response = RedirectResponse("/?utm_source=partner&utm_medium=referral", status_code=302)
    partner = partners.by_code(db, code)
    if partner:
        partner.clicks = (partner.clicks or 0) + 1
        db.commit()
        response.set_cookie(partners.COOKIE, partner.code, max_age=60 * 86400, samesite="lax", httponly=True)
    return response
