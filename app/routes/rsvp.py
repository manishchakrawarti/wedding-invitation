"""The invite experience (B6+): cinematic event page, personal guest links, RSVP and the family console."""
import csv
import io
import secrets
from functools import lru_cache
from urllib.parse import quote

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import FUNCTIONS, STYLES
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import Asset, Guest, Invitee, Order, OrderStatus, utcnow
from app import events
from app.services import demo, gifts, hires, invites
from app.services.cards import has_guest_console
from app.services.storage import storage
from app.templating import templates

router = APIRouter()

MUSIC_TYPES = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "ogg": "audio/ogg", "wav": "audio/wav"}


def get_event(slug: str, db: Session = Depends(get_db)) -> Order:
    order = db.scalar(select(Order).where(Order.rsvp_slug == slug))
    if order is None or order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(404, "Event not found")
    return order


def get_invitee(code: str, db: Session = Depends(get_db)) -> Invitee:
    invitee = db.scalar(select(Invitee).where(Invitee.code == code))
    if invitee is None or invitee.order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(404, "Invitation not found")
    return invitee


def _shaping_failed(asset: Asset) -> bool:
    return any(c["name"] == "script_shaping" and c["status"] == "fail" for c in (asset.qc or {}).get("checks", []))


def _hero(order: Order):
    """The main card shown on the invite page: the final once delivered, the watermarked proof during the
    free preview. Never one whose Indian-script text failed shaping QC (broken matras)."""
    final = next((a for a in order.live_assets("final") if a.card_key == "main"), None)
    if final is None or _shaping_failed(final):
        return None
    if order.status == OrderStatus.DELIVERED.value:
        return final
    if order.status == OrderStatus.PREVIEW.value:
        return next((a for a in order.live_assets("proof") if a.card_key == "main"), None)
    return None


def _ganesha_art(order: Order) -> str:
    """Which Ganesha drawing the page shows ("" for none): deep gold on light designs, bright gold on dark ones."""
    from app.services.cards import shows_ganesha
    from app.services.overlay import _luminance

    if not shows_ganesha(order):
        return ""
    return "ganesha-dark" if _luminance(STYLES[order.style].text_primary) < 0.3 else "ganesha"


def _music(order: Order):
    return next(iter(sorted(order.live_assets("music"), key=lambda a: a.id, reverse=True)), None)


def _experience(request: Request, order: Order, invitee: Invitee | None, thanks: bool = False, preview: bool = False):
    sched = invites.schedule(order, invitee.functions if invitee and invitee.functions else None)
    main_place = ", ".join(p for p in (order.venue_name, order.venue_address, order.city) if p)
    blessings = [(i.name, i.message) for i in order.invitees if i.message.strip()]
    blessings += [(g.name, g.message) for g in order.guests if g.message.strip()]
    return templates.TemplateResponse(
        request,
        "experience.html",
        {
            "o": order, "inv": invitee, "ev": order.event, "schedule": sched, "hero": _hero(order),
            "music": _music(order), "map_embed": invites.map_embed(main_place), "map_link": invites.map_link(main_place),
            "countdown_to": invites.main_moment(order), "gift": gifts.info(order), "food_choices": invites.FOOD_CHOICES,
            "blessings": blessings[-40:][::-1], "thanks": thanks, "preview": preview, "photos": invites.portraits(order),
            "occ": None if order.is_wedding else events.texts(order),
            "sender_phone": invites.pretty_phone(invitee.sender_phone) if invitee else "",
            "contacts": invites.contact_rows(order), "ganesha": _ganesha_art(order),
            "action": f"/i/{invitee.code}/rsvp" if invitee else f"/e/{order.rsvp_slug}/rsvp",
        },
    )


@router.get("/e/{slug}", response_class=HTMLResponse)
def event_page(request: Request, thanks: bool = False, order: Order = Depends(get_event)):
    return _experience(request, order, None, thanks)


@router.get("/i/{code}", response_class=HTMLResponse)
def personal_invite(request: Request, thanks: bool = False, preview: bool = False,
                    invitee: Invitee = Depends(get_invitee), db: Session = Depends(get_db)):
    if not preview and invitee.order.source != "demo":  # family previews and the public demo don't count as "opened"
        invitee.open_count += 1
        invitee.opened_at = invitee.opened_at or utcnow()
        db.commit()
    order = invitee.order
    if not invites.can_send(order):  # free preview: the guest's personal card; the same link becomes the full page once bought
        main = next((f for f in invites.schedule(order) if f["key"] in ("wedding", "nikah")), None) or next(iter(invites.schedule(order)), None)
        place = ", ".join(p for p in (order.venue_name, order.venue_address, order.city) if p)
        return templates.TemplateResponse(request, "guest_card.html", {
            "o": order, "inv": invitee, "preview": preview, "main": main, "map_link": invites.map_link(place),
            "sender_phone": invites.pretty_phone(invitee.sender_phone), "has_card": hires.main_final(order) is not None,
            "occ": None if order.is_wedding else events.texts(order),
        })
    return _experience(request, order, invitee, thanks, preview)


@lru_cache(maxsize=48)
def _personal_card(code: str, name: str, status: str, version: int, paid: int, updated: str = "") -> bytes:
    """Rendered once per guest and state: chat apps fetch the link-preview image several times."""
    with SessionLocal() as db:
        invitee = db.scalar(select(Invitee).where(Invitee.code == code))
        return hires.render_personal(invitee.order, hires.main_final(invitee.order), invitee)


@router.get("/i/{code}/card.jpg")
def personal_card(invitee: Invitee = Depends(get_invitee)):
    """The guest's card with their name on it (also the link-preview image in WhatsApp, Telegram, Facebook…)."""
    order = invitee.order
    if hires.main_final(order) is None or not invites.can_personalize(order):
        raise HTTPException(404)
    data = _personal_card(invitee.code, invitee.name, order.status, order.current_version, order.amount_paid + order.discount,
                          str(order.updated_at))
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=600"})


def _int(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


@router.post("/i/{code}/rsvp")
async def personal_rsvp(request: Request, invitee: Invitee = Depends(get_invitee), db: Session = Depends(get_db)):
    form = await request.form()
    attending = str(form.get("attending", "yes"))
    if attending not in ("yes", "no", "maybe"):
        attending = "yes"
    allowed = invitee.functions or [f["key"] for f in invitee.order.functions or []]
    invitee.attending = attending
    invitee.headcount = 0 if attending == "no" else _int(form.get("headcount"), 1, 1, 30)
    invitee.attending_functions = [] if attending == "no" else [k for k in form.getlist("functions") if k in allowed] or allowed
    invitee.food = str(form.get("food", "")) if form.get("food") in invites.FOOD_CHOICES else ""
    invitee.arrival_date = str(form.get("arrival_date", ""))[:20]
    invitee.arrival_mode = str(form.get("arrival_mode", ""))[:20] if form.get("arrival_date") else ""
    invitee.needs_pickup = bool(form.get("needs_pickup")) and bool(form.get("arrival_date"))
    invitee.message = str(form.get("message", "")).strip()[:1000]
    invitee.responded_at = utcnow()
    db.commit()
    return RedirectResponse(f"/i/{invitee.code}?thanks=1#rsvp", status_code=303)


@router.post("/e/{slug}/rsvp")
async def public_rsvp(request: Request, order: Order = Depends(get_event), db: Session = Depends(get_db)):
    """RSVP from the general event link (guests without a personal invite)."""
    form = await request.form()
    name = str(form.get("name", "")).strip()[:120]
    attending = str(form.get("attending", "yes"))
    if not name or attending not in ("yes", "no", "maybe"):
        return RedirectResponse(f"/e/{order.rsvp_slug}#rsvp", status_code=303)
    db.add(Guest(
        order_id=order.id, name=name, phone=str(form.get("phone", "")).strip()[:20], attending=attending,
        headcount=0 if attending == "no" else _int(form.get("headcount"), 1, 1, 20),
        functions=[k for k in form.getlist("functions") if k in FUNCTIONS],
        message=str(form.get("message", "")).strip()[:1000],
    ))
    db.commit()
    return RedirectResponse(f"/e/{order.rsvp_slug}?thanks=1#rsvp", status_code=303)


@router.get("/e/{slug}/invite")
def invite_image(order: Order = Depends(get_event)):
    hero = _hero(order)
    if hero is None:
        raise HTTPException(404)
    return Response(storage.read(hero.path), media_type=hero.content_type)


@router.get("/e/{slug}/music")
def music(order: Order = Depends(get_event)):
    track = _music(order)
    if track is None:
        raise HTTPException(404)
    return Response(storage.read(track.path), media_type=track.content_type)


def _png_qr(data: str) -> Response:
    buf = io.BytesIO()
    qrcode.make(data, box_size=10, border=2).save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@router.get("/e/{slug}/portrait/{role}")
def portrait(role: str, order: Order = Depends(get_event)):
    photo = invites.portraits(order).get(role)
    if photo is None:
        raise HTTPException(404)
    return Response(storage.read(photo.path), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/e/{slug}/qr.png")
def qr(order: Order = Depends(get_event)):
    return _png_qr(f"{settings.base_url}/e/{order.rsvp_slug}")


@router.get("/e/{slug}/shagun.png")
def shagun_qr(order: Order = Depends(get_event)):
    link = gifts.upi_link(order)
    if not link:
        raise HTTPException(404)
    return _png_qr(link)


@router.get("/e/{slug}/gift-qr")
def gift_qr(order: Order = Depends(get_event)):
    """The QR guests scan to send a gift: the family's own payment QR, else one made from their UPI ID."""
    found = gifts.qr_bytes(order)
    if found is None:
        raise HTTPException(404)
    data, mime = found
    return Response(data, media_type=mime, headers={"Cache-Control": "no-cache"})


@router.get("/e/{slug}/calendar/{key}.ics")
def calendar(key: str, order: Order = Depends(get_event)):
    fn = next((f for f in invites.schedule(order) if f["key"] == key), None)
    if fn is None:
        raise HTTPException(404)
    return Response(invites.ics(order, fn), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{key}.ics"'})


def _ready_demo(lang: str, event: str = "wedding") -> Order:
    if event and event != "wedding":
        if event not in events.TYPES:
            raise HTTPException(404, "No demo for that occasion")
        lang = "en"  # event demos are in English
    elif lang not in demo.DEMOS:
        raise HTTPException(404, "No demo in that language")
    order = demo.demo_order(lang, event or "wedding")
    if order is None or order.status != OrderStatus.DELIVERED.value:
        raise HTTPException(503, "The demo is being prepared, please try again in a minute.")
    return order


@router.get("/demo/event/{event}/console")
@router.get("/demo/console")  # registered before /demo/{lang} so "console" isn't read as a language
@router.get("/demo/{lang}/console")
def demo_console(lang: str = "en", event: str = "wedding"):
    """Live sample of the family console."""
    order = _ready_demo(lang, event)
    return RedirectResponse(f"/e/{order.rsvp_slug}/guests?key={order.token}", status_code=302)


@router.get("/demo/event/{event}")
@router.get("/demo")
@router.get("/demo/{lang}")
def demo_invite(lang: str = "en", event: str = "wedding"):
    """Live sample invite for marketing: what a guest receives, for any occasion and (weddings) language."""
    order = _ready_demo(lang, event)
    with SessionLocal() as db:
        invitee = db.scalar(select(Invitee).where(Invitee.order_id == order.id).order_by(Invitee.id))
    return RedirectResponse(f"/i/{invitee.code}", status_code=302)


# --- family console ------------------------------------------------------------

def _check_key(order: Order, key: str) -> None:
    if not secrets.compare_digest(key or "", order.token):
        raise HTTPException(403, "Invalid link")
    if not has_guest_console(order):
        raise HTTPException(403, "Personal guest invites and RSVP tracking are part of Premium. Message us on WhatsApp to upgrade.")


def _console(slug: str, key: str, msg: str = "") -> RedirectResponse:
    return RedirectResponse(f"/e/{slug}/guests?key={key}" + (f"&msg={quote(msg)}" if msg else ""), status_code=303)


@router.get("/e/{slug}/guests", response_class=HTMLResponse)
def family_console(request: Request, key: str = "", msg: str = "", order: Order = Depends(get_event), db: Session = Depends(get_db)):
    _check_key(order, key)
    invites.event_details(db, order)
    db.commit()
    rows = [invites.send_row(order, i) for i in order.invitees]
    sender_name, sender_phone = invites.last_sender(order)
    return templates.TemplateResponse(request, "family.html", {
        "o": order, "ev": order.event, "rows": rows, "walk_ins": sorted(order.guests, key=lambda g: g.created_at, reverse=True),
        "stats": invites.stats(order), "key": key, "msg": msg, "schedule": invites.schedule(order),
        "music": _music(order), "food_choices": invites.FOOD_CHOICES, "days": invites.days_until(order),
        "photos": invites.portraits(order), "photo_roles": invites.PORTRAIT_ROLES, "gift": gifts.info(order),
        "sender_name": sender_name, "sender_phone": invites.pretty_phone(sender_phone), "can_pdf": invites.can_send(order),
    })


@router.post("/e/{slug}/guests/add")
async def add_guests(request: Request, order: Order = Depends(get_event), db: Session = Depends(get_db)):
    form = await request.form()
    key = str(form.get("key", ""))
    _check_key(order, key)
    available = [f["key"] for f in order.functions or []]
    defaults = [k for k in form.getlist("default_functions") if k in available]
    parsed = invites.parse_guest_lines(str(form.get("guests", "")), available, defaults)
    sender, error = invites.read_sender(form)
    if error:
        return _console(order.rsvp_slug, key, error)
    for g in parsed[:2000]:
        db.add(Invitee(order_id=order.id, code=invites.new_code(db), **sender, **g))
        db.flush()
    db.commit()
    return _console(order.rsvp_slug, key, f"Added {len(parsed)} guest(s). Tap 'Send' to WhatsApp each personal invite.")


@router.post("/e/{slug}/guests/{invitee_id}/sent")
async def mark_sent(request: Request, invitee_id: int, order: Order = Depends(get_event), db: Session = Depends(get_db)):
    _check_key(order, str((await request.form()).get("key", "")))
    invitee = next((i for i in order.invitees if i.id == invitee_id), None)
    if invitee and not invitee.sent_at:
        invitee.sent_at = utcnow()
        db.commit()
    return {"ok": True}


@router.post("/e/{slug}/guests/{invitee_id}/delete")
async def delete_guest(request: Request, invitee_id: int, order: Order = Depends(get_event), db: Session = Depends(get_db)):
    key = str((await request.form()).get("key", ""))
    _check_key(order, key)
    invitee = next((i for i in order.invitees if i.id == invitee_id), None)
    if invitee:
        db.delete(invitee)
        db.commit()
    return _console(order.rsvp_slug, key, "Guest removed.")


@router.post("/e/{slug}/details")
async def save_details(request: Request, order: Order = Depends(get_event), db: Session = Depends(get_db)):
    form = await request.form()
    key = str(form.get("key", ""))
    _check_key(order, key)
    ev = invites.event_details(db, order)
    for field, limit in (("hosts", 200), ("blessing_line", 300), ("story", 3000), ("hashtag", 60), ("livestream_url", 300)):
        setattr(ev, field, str(form.get(field, "")).strip()[:limit])
    ev.dress_codes = {f["key"]: str(form.get(f"dress_{f['key']}", "")).strip()[:120] for f in order.functions or []}
    errors: list[str] = []
    family = invites.read_family_details(form, errors)
    family.pop("blessing_line")  # saved with the other text fields above
    if not errors:
        invites.save_family_details(db, order, family)
    gift = await gifts.read_gift_form(form, errors)
    if not errors:
        gifts.save(db, order, gift)
    new_photos = await invites.read_portrait_uploads(form, errors)
    enhance = str(form.get("enhance_photos", "on")) != "off"
    for role, data in new_photos.items():
        invites.save_portrait(db, order, role, data, enhance=enhance)
    if errors:
        db.commit()
        return _console(order.rsvp_slug, key, " ".join(errors))
    upload = form.get("music")
    if getattr(upload, "filename", ""):
        ext = upload.filename.rsplit(".", 1)[-1].lower()
        data = await upload.read()
        if ext not in MUSIC_TYPES or len(data) > 15 * 1024 * 1024:
            return _console(order.rsvp_slug, key, "Music must be an MP3/M4A/OGG/WAV under 15 MB.")
        path = storage.save(f"orders/{order.public_id}/music/{secrets.token_hex(4)}.{ext}", data)
        db.add(Asset(order_id=order.id, kind="music", card_key="music", path=path, content_type=MUSIC_TYPES[ext]))
    db.commit()
    if new_photos and enhance:
        from app.services import pipeline
        from app.services.photo_enhance import ai_upgrade_portraits

        pipeline.run_background(ai_upgrade_portraits, order.id)
    return _console(order.rsvp_slug, key, "Invitation page updated." + (" Photos enhanced ✨" if new_photos and enhance else ""))


@router.get("/e/{slug}/guests.csv")
def guests_csv(key: str = "", order: Order = Depends(get_event)):
    _check_key(order, key)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "side", "invited_to", "personal_link", "sent", "opened", "times_opened", "reply",
                "people", "attending_functions", "food", "arrival_date", "arrival_by", "needs_pickup", "message"])
    for i in order.invitees:
        w.writerow([i.name, i.phone, i.side, " ".join(i.functions) or "all", invites.invite_url(i), bool(i.sent_at),
                    bool(i.opened_at), i.open_count, i.attending or "no reply", i.headcount, " ".join(i.attending_functions or []),
                    i.food, i.arrival_date, i.arrival_mode, i.needs_pickup, i.message])
    for g in order.guests:
        w.writerow([g.name, g.phone, "", "via event link", "", "", "", "", g.attending, g.headcount, " ".join(g.functions or []),
                    "", "", "", "", g.message])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="guests-{order.rsvp_slug}.csv"'})
