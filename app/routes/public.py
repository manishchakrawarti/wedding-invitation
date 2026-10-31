"""Customer-facing pages: landing (B1), order form (B2), payment (B3), proof approval (B4), delivery (B5)."""
import io
import secrets
import time
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import ADDONS, FUNCTIONS, LANGUAGES, PACKAGES, STYLES
from app.config import settings
from app.db import get_db
from app.models import Asset, EventDetails, Order, OrderStatus
from app.services import notify, orders, payments, pipeline
from app.services.cards import has_guest_console
from app.services.maintenance import sample_image
from app.services.storage import storage
from app.templating import templates
from app.utils import new_token, normalize_phone, slugify

router = APIRouter()

MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 10 * 1024 * 1024
PROOF_VISIBLE = {
    OrderStatus.PREVIEW.value,
    OrderStatus.PROOF_SENT.value,
    OrderStatus.CHANGES_REQUESTED.value,
    OrderStatus.BALANCE_DUE.value,
    OrderStatus.DELIVERED.value,
}


def get_order(token: str, db: Session = Depends(get_db)) -> Order:
    order = db.scalar(select(Order).where(Order.token == token))
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"packages": PACKAGES, "addons": ADDONS, "styles": STYLES})


@router.get("/samples/{style_key}.jpg")
def sample(style_key: str):
    if style_key not in STYLES:
        raise HTTPException(404)
    return Response(sample_image(style_key), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/terms", response_class=HTMLResponse)
@router.get("/privacy", response_class=HTMLResponse)
@router.get("/refund", response_class=HTMLResponse)
def legal(request: Request):
    page = request.url.path.strip("/")
    return templates.TemplateResponse(request, "legal.html", {"page": page})


# --- order form ---------------------------------------------------------------

def is_test_code(code: str) -> bool:
    return bool(settings.test_order_code) and secrets.compare_digest(code or "", settings.test_order_code)


def _form_context(values: dict | None = None, errors: list[str] | None = None) -> dict:
    values = values or {}
    return {
        "packages": PACKAGES, "addons": ADDONS, "styles": STYLES, "languages": LANGUAGES,
        "functions": FUNCTIONS, "v": values, "errors": errors or [], "max_photos": MAX_PHOTOS,
        "today": date.today().isoformat(), "test_mode": is_test_code(values.get("test", "")),
    }


@router.get("/order", response_class=HTMLResponse)
def order_form(request: Request, package: str = "video", style: str = "north_indian", ref: str = "", test: str = ""):
    values = {
        "package": package if package in PACKAGES else "video",
        "style": style if style in STYLES else "north_indian",
        "language": "en", "payment_option": "full", "referral": ref, "fn_wedding": "on",
        "test": test if is_test_code(test) else "",
    }
    return templates.TemplateResponse(request, "order_form.html", _form_context(values))


def _clean_photo(data: bytes) -> bytes:
    """Fix rotation, downscale and re-encode — this also strips EXIF (incl. GPS location)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _parse_functions(form, wedding_date: date | None, errors: list[str]) -> list[dict]:
    functions = []
    for key in FUNCTIONS:
        if form.get(f"fn_{key}"):
            fn_date = str(form.get(f"fn_{key}_date") or "").strip() or (wedding_date.isoformat() if wedding_date else "")
            try:
                date.fromisoformat(fn_date)
            except ValueError:
                errors.append(f"Please give a valid date for {FUNCTIONS[key]}.")
                continue
            functions.append({
                "key": key, "date": fn_date,
                "time": str(form.get(f"fn_{key}_time") or "").strip(),
                "venue": str(form.get(f"fn_{key}_venue") or "").strip(),
            })
    return functions


@router.post("/order")
async def submit_order(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    def f(key: str) -> str:
        return str(form.get(key) or "").strip()

    values = {k: f(k) for k in form.keys() if k not in ("photos", "addons")}
    values["addons"] = form.getlist("addons")
    errors: list[str] = []

    for key, label in [("customer_name", "Your name"), ("bride_name", "Bride's name"), ("groom_name", "Groom's name"), ("venue_name", "Venue")]:
        if not f(key):
            errors.append(f"{label} is required.")
    phone = normalize_phone(f("phone"))
    if len(phone) < 11:
        errors.append("Please enter a valid WhatsApp number.")
    if f("email") and "@" not in f("email"):
        errors.append("Please enter a valid email address or leave it empty.")
    try:
        wedding_date = date.fromisoformat(f("wedding_date"))
        if wedding_date < date.today():
            errors.append("The wedding date is in the past.")
    except ValueError:
        wedding_date = None
        errors.append("Please choose the wedding date.")
    package, style, language = f("package"), f("style"), f("language")
    if package not in PACKAGES or not PACKAGES[package].listed or style not in STYLES or language not in LANGUAGES:
        errors.append("Please choose a package, style and language.")
    if language != "en" and not (f("bride_name_local") and f("groom_name_local")):
        errors.append(f"Please write both names in {LANGUAGES.get(language, LANGUAGES['en']).name} script too, exactly as they should appear.")
    payment_option = f("payment_option") if f("payment_option") in ("full", "advance") else "full"
    if not form.get("accept_terms"):
        errors.append("Please accept the terms, privacy and refund policy.")

    functions = _parse_functions(form, wedding_date, errors)

    uploads = [u for u in form.getlist("photos") if getattr(u, "filename", "")]
    photo_bytes: list[bytes] = []
    if len(uploads) > MAX_PHOTOS:
        errors.append(f"Please upload at most {MAX_PHOTOS} photos.")
    if uploads and not form.get("photo_consent"):
        errors.append("Please confirm photo consent to use your photos.")
    for upload in uploads[:MAX_PHOTOS]:
        data = await upload.read()
        if len(data) > MAX_PHOTO_BYTES:
            errors.append(f"{upload.filename} is larger than 10 MB.")
            continue
        try:
            photo_bytes.append(_clean_photo(data))
        except (UnidentifiedImageError, OSError):
            errors.append(f"{upload.filename} is not a JPG/PNG/WebP photo (iPhone HEIC: please export as JPG).")

    referral = f("referral").upper()
    referral_ok = orders.valid_referral(db, referral)
    if referral and not referral_ok:
        errors.append("That referral code was not found — remove it or check the spelling.")

    if errors:
        return templates.TemplateResponse(request, "order_form.html", _form_context(values, errors), status_code=422)

    addons = orders.effective_addons(package, values["addons"])
    subtotal, discount, total = orders.price(package, addons, referral_ok)
    test_order = is_test_code(f("test"))
    if test_order:  # owner's ₹1 test: real flow, token price, kept out of revenue stats
        total = settings.test_order_price_inr * 100
        discount, payment_option = subtotal - total, "full"
    order = Order(
        public_id=orders.new_public_id(db), token=new_token(), status=OrderStatus.PENDING_PAYMENT.value,
        customer_name=f("customer_name"), phone=phone, email=f("email"),
        bride_name=f("bride_name"), groom_name=f("groom_name"),
        bride_name_local=f("bride_name_local"), groom_name_local=f("groom_name_local"),
        bride_family=f("bride_family"), groom_family=f("groom_family"),
        wedding_date=wedding_date, venue_name=f("venue_name"), venue_address=f("venue_address"), city=f("city"),
        language=language, style=style, package=package, addons=addons, functions=functions,
        customer_notes=f("notes"), photo_consent=bool(form.get("photo_consent")),
        marketing_consent=bool(form.get("marketing_consent")),
        referral_code=orders.new_referral_code(db, f("bride_name")), referred_by_code=referral if referral_ok else "",
        payment_option=payment_option, subtotal=subtotal, discount=discount, total=total,
        source="test" if test_order else "website",
    )
    db.add(order)
    db.flush()
    for i, data in enumerate(photo_bytes, 1):
        key = storage.save(f"orders/{order.public_id}/photos/{i}.jpg", data)
        db.add(Asset(order_id=order.id, kind="photo", card_key=f"photo{i}", path=key, content_type="image/jpeg"))
    orders.log_event(db, order, f"Order placed: {PACKAGES[package].name}, {STYLES[style].name}, {LANGUAGES[language].name}")
    db.commit()
    notify.notify_customer(db, order, "order_received")
    return redirect(f"/o/{order.token}/pay")


# --- order status, payment, proof, delivery -----------------------------------------

@router.get("/o/{token}", response_class=HTMLResponse)
def order_status(request: Request, order: Order = Depends(get_order)):
    if order.source == "instant" and order.status != OrderStatus.DELIVERED.value:
        return redirect(f"/o/{order.token}/preview")
    return templates.TemplateResponse(
        request, "order_status.html", {"o": order, "visible": PROOF_VISIBLE, "console": has_guest_console(order)}
    )


def _allowed_purposes(order: Order) -> list[str]:
    if order.status == OrderStatus.PENDING_PAYMENT.value:
        return ["full", "advance"]
    if order.status == OrderStatus.PREVIEW.value:
        return ["full"] if orders.preview_unlockable(order) else []
    allowed = []
    if order.amount_paid and order.balance_due:
        allowed.append("balance")
    if order.status == OrderStatus.PROOF_SENT.value and order.revisions_left == 0:
        allowed.append("revision")
    return allowed


@router.get("/o/{token}/pay", response_class=HTMLResponse)
def pay(request: Request, purpose: str = "", order: Order = Depends(get_order), db: Session = Depends(get_db)):
    allowed = _allowed_purposes(order)
    if not allowed:
        return redirect(f"/o/{order.token}")
    if purpose not in allowed:
        purpose = order.payment_option if order.status == OrderStatus.PENDING_PAYMENT.value else allowed[0]
    if purpose in ("full", "advance") and order.payment_option != purpose:
        order.payment_option = purpose
        db.commit()
    payment = payments.create_payment(db, order, purpose)
    return templates.TemplateResponse(request, "pay.html", {"o": order, "p": payment, "allowed": allowed})


@router.post("/o/{token}/pay/verify")
async def pay_verify(request: Request, order: Order = Depends(get_order), db: Session = Depends(get_db)):
    form = await request.form()
    provider_order_id = str(form.get("razorpay_order_id", ""))
    payment = payments.find_by_provider_order(db, provider_order_id)
    if payment is None or payment.order_id != order.id:
        raise HTTPException(400, "Unknown payment")
    if not payments.verify_checkout_signature(provider_order_id, str(form.get("razorpay_payment_id", "")), str(form.get("razorpay_signature", ""))):
        raise HTTPException(400, "Payment signature mismatch — if money was debited, it will be confirmed automatically.")
    payments.mark_paid(db, payment, str(form.get("razorpay_payment_id")))
    return redirect(f"/o/{order.token}?paid=1")


@router.post("/o/{token}/pay/simulate/{payment_id}")
def pay_simulate(payment_id: int, order: Order = Depends(get_order), db: Session = Depends(get_db)):
    payment = next((p for p in order.payments if p.id == payment_id), None)
    if payment is None or payment.provider != "mock" or settings.payment_provider != "mock":
        raise HTTPException(404)
    payments.mark_paid(db, payment, "simulated")
    return redirect(f"/o/{order.token}?paid=1")


@router.post("/o/{token}/pay/claim/{payment_id}")
async def pay_claim(request: Request, payment_id: int, order: Order = Depends(get_order), db: Session = Depends(get_db)):
    payment = next((p for p in order.payments if p.id == payment_id), None)
    if payment is None or payment.provider != "manual" or payment.status not in ("created", "claimed"):
        raise HTTPException(404)
    reference = str((await request.form()).get("reference", "")).strip()
    if not reference:
        return redirect(f"/o/{order.token}/pay?purpose={payment.purpose}")
    payments.claim_manual_payment(db, payment, reference)
    return redirect(f"/o/{order.token}/pay?purpose={payment.purpose}")


@router.get("/o/{token}/proof", response_class=HTMLResponse)
def proof(request: Request, order: Order = Depends(get_order)):
    if order.status not in PROOF_VISIBLE:
        return redirect(f"/o/{order.token}")
    proofs = order.live_assets("proof")
    return templates.TemplateResponse(request, "proof.html", {"o": order, "proofs": proofs})


@router.post("/o/{token}/proof/approve")
def proof_approve(order: Order = Depends(get_order), db: Session = Depends(get_db)):
    if order.status != OrderStatus.PROOF_SENT.value:
        return redirect(f"/o/{order.token}")
    orders.approve_proof(db, order)
    return redirect(f"/o/{order.token}")


@router.post("/o/{token}/proof/changes")
async def proof_changes(request: Request, order: Order = Depends(get_order), db: Session = Depends(get_db)):
    form = await request.form()
    notes = str(form.get("notes", "")).strip()
    if order.status != OrderStatus.PROOF_SENT.value or not notes:
        return redirect(f"/o/{order.token}/proof")
    if not orders.request_changes(db, order, notes):
        return redirect(f"/o/{order.token}/pay?purpose=revision")
    return redirect(f"/o/{order.token}?changes=1")


@router.get("/o/{token}/files/{asset_id}")
def order_file(asset_id: int, download: bool = False, order: Order = Depends(get_order)):
    asset = next((a for a in order.assets if a.id == asset_id and a.deleted_at is None), None)
    if asset is None:
        raise HTTPException(404)
    delivered = order.status == OrderStatus.DELIVERED.value
    if asset.kind == "proof":
        if order.status not in PROOF_VISIBLE or asset.version != order.current_version:
            raise HTTPException(404)
    elif asset.kind in ("final", "video"):
        if not delivered:
            raise HTTPException(403, "Available after approval and full payment")
    else:
        raise HTTPException(404)
    headers = {}
    if download:
        ext = asset.path.rsplit(".", 1)[-1]
        name = f"{slugify(f'{order.bride_name}-{order.groom_name}-{asset.card_key}') or 'invitation'}.{ext}"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(storage.read(asset.path), media_type=asset.content_type, headers=headers)


# --- ₹99 instant invitation: free preview, pay to unlock ---------------------------

_preview_hits: dict[str, list[float]] = defaultdict(list)


def _too_many_previews(ip: str) -> bool:
    """Free previews cost us AI image credits, so cap them per visitor per hour."""
    now = time.time()
    hits = [t for t in _preview_hits[ip] if now - t < 3600]
    _preview_hits[ip] = hits
    if len(hits) >= settings.instant_previews_per_hour:
        return True
    hits.append(now)
    return False


def _create_context(values: dict, errors: list[str] | None = None) -> dict:
    return {
        "styles": STYLES, "languages": LANGUAGES, "functions": FUNCTIONS, "v": values, "errors": errors or [],
        "today": date.today().isoformat(), "pkg": PACKAGES["instant"],
    }


@router.get("/create", response_class=HTMLResponse)
def create_form(request: Request, style: str = "north_indian", lang: str = "en"):
    values = {"style": style if style in STYLES else "north_indian", "language": lang if lang in LANGUAGES else "en", "fn_wedding": "on"}
    return templates.TemplateResponse(request, "create.html", _create_context(values))


@router.post("/create")
async def create_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    def f(key: str) -> str:
        return str(form.get(key) or "").strip()

    values = {k: f(k) for k in form.keys()}
    errors: list[str] = []
    for key, label in [("bride_name", "Bride's name"), ("groom_name", "Groom's name"), ("venue_name", "Venue")]:
        if not f(key):
            errors.append(f"{label} is required.")
    try:
        wedding_date = date.fromisoformat(f("wedding_date"))
        if wedding_date < date.today():
            errors.append("The wedding date is in the past.")
    except ValueError:
        wedding_date = None
        errors.append("Please choose the wedding date.")
    style, language = f("style"), f("language")
    if style not in STYLES or language not in LANGUAGES:
        errors.append("Please choose a style and language.")
    if f("email") and "@" not in f("email"):
        errors.append("Please enter a valid email address or leave it empty.")
    functions = _parse_functions(form, wedding_date, errors)
    if not any(fn["key"] in ("wedding", "nikah") for fn in functions) and wedding_date:
        functions.append({"key": "nikah" if style == "muslim_nikah" else "wedding", "date": wedding_date.isoformat(),
                          "time": f("wedding_time"), "venue": ""})
    else:
        for fn in functions:
            if fn["key"] in ("wedding", "nikah") and not fn["time"]:
                fn["time"] = f("wedding_time")
    if not errors and _too_many_previews(request.client.host if request.client else "unknown"):
        errors.append("You've created several previews this hour. Please try again a little later, or message us on WhatsApp.")
    if errors:
        return templates.TemplateResponse(request, "create.html", _create_context(values, errors), status_code=422)

    price = PACKAGES["instant"].price * 100
    order = Order(
        public_id=orders.new_public_id(db), token=new_token(), status=OrderStatus.QUEUED.value, source="instant",
        customer_name=f("customer_name"), phone=normalize_phone(f("phone")) if f("phone") else "", email=f("email"),
        bride_name=f("bride_name"), groom_name=f("groom_name"),
        bride_name_local=f("bride_name_local") if language != "en" else "",
        groom_name_local=f("groom_name_local") if language != "en" else "",
        bride_family=f("bride_family"), groom_family=f("groom_family"),
        wedding_date=wedding_date, venue_name=f("venue_name"), venue_address=f("venue_address"), city=f("city"),
        language=language, style=style, package="instant", addons=[], functions=sorted(functions, key=lambda x: x["date"]),
        referral_code=orders.new_referral_code(db, f("bride_name")), payment_option="full",
        subtotal=price, discount=0, total=price,
    )
    db.add(order)
    db.flush()
    if f("hosts"):
        db.add(EventDetails(order_id=order.id, hosts=f("hosts")[:200], dress_codes={}))
    orders.log_event(db, order, f"Instant invitation created: {STYLES[style].name}, {LANGUAGES[language].name}")
    db.commit()
    pipeline.enqueue(order.id)
    return redirect(f"/o/{order.token}/preview")


@router.get("/o/{token}/preview", response_class=HTMLResponse)
def preview(request: Request, order: Order = Depends(get_order)):
    if order.status == OrderStatus.DELIVERED.value:
        return redirect(f"/o/{order.token}")
    working = order.status in (OrderStatus.QUEUED.value, OrderStatus.GENERATING.value)
    return templates.TemplateResponse(request, "preview.html", {
        "o": order, "working": working, "proofs": order.live_assets("proof"),
        "unlockable": orders.preview_unlockable(order), "pkg": PACKAGES[order.package],
    })


@router.post("/o/{token}/email")
async def email_invite(request: Request, order: Order = Depends(get_order), db: Session = Depends(get_db)):
    email = str((await request.form()).get("email", "")).strip()
    if order.status != OrderStatus.DELIVERED.value:
        return redirect(f"/o/{order.token}")
    if "@" not in email:
        return redirect(f"/o/{order.token}?emailed=invalid#email")
    order.email = order.email or email
    attachments = []
    for asset in order.live_assets("final"):
        if asset.content_type == "image/png":
            name = f"{slugify(order.bride_name + '-' + order.groom_name + '-' + asset.card_key) or 'invitation'}.png"
            attachments.append((name, storage.read(asset.path), "image/png"))
    page = f"\nYour invitation page to share with guests: {settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug else ""
    body = (
        f"Namaste! 🙏\n\nHere is your wedding invitation for {order.bride_name} & {order.groom_name} "
        f"({len(attachments)} card(s) attached).\n\nDownload anytime: {notify.order_url(order)}{page}\n\n"
        f"Wishing you a beautiful wedding,\n{settings.brand_name}"
    )
    note = notify.send(db, "email", email, body, subject=f"Your wedding invitation: {order.bride_name} & {order.groom_name}",
                       order=order, attachments=attachments)
    return redirect(f"/o/{order.token}?emailed={note.status}#email")
