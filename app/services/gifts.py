"""Gifts (shagun) by UPI for every occasion: guests pay the family directly, using the family's UPI ID,
their UPI-linked mobile number or their own payment QR code (GPay / PhonePe / Paytm / bank). We never
touch the money; we only show guests where to send it."""
import io
import re
import secrets
from urllib.parse import parse_qs, quote, urlparse

from sqlalchemy.orm import Session

from app.models import Asset, Order, utcnow
from app.services import invites
from app.services.storage import storage

UPI_RE = re.compile(r"^[A-Za-z0-9._-]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")
MAX_QR_BYTES = 5 * 1024 * 1024


def clean_upi(raw: str) -> str:
    return re.sub(r"\s+", "", raw or "")[:100]


def clean_mobile(raw: str) -> str:
    """A 10-digit Indian mobile number (6-9...), or "" if it isn't one."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else ""


def pretty_mobile(digits: str) -> str:
    return f"+91 {digits[:5]} {digits[5:]}" if len(digits) == 10 else digits


def decode_qr(data: bytes) -> str:
    """The text inside a QR code image ("" if none could be read). Tries a few sizes: payment-app
    screenshots are often large, and photos of printed QR stands small or soft."""
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    except OSError:
        return ""
    detector = cv2.QRCodeDetector()
    for side in (None, 1000, 600, 1600):
        candidate = img
        if side:
            candidate = img.copy()
            scale = side / max(img.size)
            candidate = candidate.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        try:
            text, _, _ = detector.detectAndDecode(np.array(candidate))
        except cv2.error:
            text = ""
        if text:
            return text.strip()
    return ""


def upi_from_qr_text(text: str) -> tuple[str, str]:
    """(UPI ID, payee name) from a UPI payment QR ("upi://pay?pa=...&pn=..."), else ("", "")."""
    if not text.lower().startswith("upi://"):
        return "", ""
    query = parse_qs(urlparse(text).query)
    upi = clean_upi((query.get("pa") or [""])[0])
    return (upi if UPI_RE.match(upi) else ""), (query.get("pn") or [""])[0].strip()[:100]


def _clean_qr_image(data: bytes) -> bytes:
    """Rotate, cap the size and re-encode as PNG (keeps QR edges sharp; strips metadata)."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


async def read_gift_form(form, errors: list[str], kept_qr: bytes | None = None) -> dict:
    """Validate the gift fields (gift_upi, gift_phone, gift_name, gift_qr file, gift_qr_remove). kept_qr: a QR
    already accepted on an earlier try of the same form, used if no new file was chosen."""
    from PIL import UnidentifiedImageError

    upi = clean_upi(str(form.get("gift_upi") or ""))
    raw_phone = str(form.get("gift_phone") or "").strip()
    phone = clean_mobile(raw_phone)
    name = str(form.get("gift_name") or "").strip()[:100]
    if upi and not UPI_RE.match(upi):
        errors.append("The UPI ID doesn't look right. It looks like name@okhdfcbank or 9876543210@ybl.")
    if raw_phone and not phone:
        errors.append("Please enter a 10-digit mobile number for gifts (the one linked to your UPI), or leave it empty.")
    qr = None
    upload = form.get("gift_qr")
    data = await upload.read() if getattr(upload, "filename", "") else kept_qr
    if data:
        if len(data) > MAX_QR_BYTES:
            errors.append("The payment QR image is larger than 5 MB.")
        else:
            try:
                qr = _clean_qr_image(data)
            except (UnidentifiedImageError, OSError):
                errors.append("The payment QR must be a JPG, PNG or WebP image (a screenshot from your UPI app is perfect).")
            else:
                text = decode_qr(qr)
                qr_upi, qr_name = upi_from_qr_text(text)
                if text and not qr_upi:
                    errors.append("That QR code isn't a UPI payment QR. In GPay / PhonePe / Paytm open \"Receive money\" or "
                                  "\"My QR\" and upload a screenshot of that.")
                    qr = None
                else:
                    upi = upi or qr_upi  # read the UPI ID from the QR so the "Pay" button works too
                    name = name or qr_name
    return {"upi_id": upi, "gift_phone": phone, "gift_name": name, "qr": qr,
            "remove_qr": bool(form.get("gift_qr_remove"))}


def qr_asset(order: Order) -> Asset | None:
    return next(iter(sorted(order.live_assets("gift_qr"), key=lambda a: a.id, reverse=True)), None)


def save(db: Session, order: Order, gift: dict) -> None:
    ev = invites.event_details(db, order)
    ev.upi_id, ev.gift_phone, ev.gift_name = gift["upi_id"], gift["gift_phone"], gift["gift_name"]
    if gift.get("qr") or gift.get("remove_qr"):
        for old in order.live_assets("gift_qr"):
            storage.delete(old.path)
            old.deleted_at = utcnow()
    if gift.get("qr"):
        path = storage.save(f"orders/{order.public_id}/gift/qr_{secrets.token_hex(4)}.png", gift["qr"])
        db.add(Asset(order_id=order.id, kind="gift_qr", card_key="gift_qr", path=path, content_type="image/png"))
        db.flush()


def upi_link(order: Order) -> str:
    ev = order.event
    if not ev or not ev.upi_id:
        return ""
    names = order.display_names
    note = ("Shagun for " if order.is_wedding else "Gift for ") + names
    return f"upi://pay?pa={quote(ev.upi_id)}&pn={quote(ev.gift_name or names)}&cu=INR&tn={quote(note[:50])}"


def info(order: Order) -> dict | None:
    """What the invite shows under "Send a gift", or None if the family hasn't added any way to receive gifts."""
    ev = order.event
    qr = qr_asset(order)
    if not ev or not (ev.upi_id or ev.gift_phone or qr):
        return None
    link = upi_link(order)
    return {
        "upi_id": ev.upi_id, "phone": ev.gift_phone, "phone_pretty": pretty_mobile(ev.gift_phone),
        "payee": ev.gift_name or order.display_names, "link": link, "uploaded_qr": qr,
        "qr_src": f"/e/{order.rsvp_slug}/gift-qr" if order.rsvp_slug and (qr or link) else "",
    }


def qr_bytes(order: Order) -> tuple[bytes, str] | None:
    """The QR image guests scan: the family's own, else one generated from their UPI ID."""
    asset = qr_asset(order)
    if asset:
        return storage.read(asset.path), "image/png"
    link = upi_link(order)
    if not link:
        return None
    import qrcode

    buf = io.BytesIO()
    qrcode.make(link, border=2).save(buf, "PNG")
    return buf.getvalue(), "image/png"
