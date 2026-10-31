"""Make the couple's and family's photos look their best before they go on the invitation.

1. Smart framing: faces are detected so the bride/groom sit centred in their circle and
   nobody in the family photo is cut off.
2. Studio finish (always, free): balanced colour, lifted exposure for dull photos, warmer
   wedding tones, crisper detail and a soft glow.
3. AI retouch (when Gemini is enabled): professional lighting/sharpness/noise clean-up that
   must keep faces unchanged. If a face can no longer be found afterwards, the AI result is
   discarded and the studio-finished photo is used instead.
"""
import io
import logging

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat

from app.config import settings

log = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np

    _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if _CASCADE.empty():
        _CASCADE = None
except Exception:  # noqa: BLE001 — OpenCV is optional; framing falls back to a sensible centre crop
    cv2 = None
    _CASCADE = None

AI_PROMPT = (
    "Retouch this photo to professional wedding-portrait quality: flattering soft lighting, accurate natural "
    "skin tones, gentle warm golden tone, crisp focus, remove noise, blur and colour casts. "
    "Keep every person's face, identity, expression, age, body, hair, clothing and jewellery exactly the same. "
    "Do not add, remove or move people. Keep the composition. Photorealistic, no text, no borders."
)


def detect_faces(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Face boxes (x, y, w, h) in img's coordinates, largest first. Empty if OpenCV isn't available."""
    if _CASCADE is None:
        return []
    scale = min(1.0, 1500 / max(img.size))
    small = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale)))) if scale < 1 else img
    gray = cv2.cvtColor(np.array(small.convert("RGB")), cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    min_side = max(24, int(min(small.size) * 0.04))
    found = _CASCADE.detectMultiScale(gray, scaleFactor=1.06, minNeighbors=5, minSize=(min_side, min_side))
    boxes = [tuple(int(v / scale) for v in box) for box in found]
    return sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)


def _clamp_box(cx: float, cy: float, w: float, h: float, img: Image.Image) -> tuple[int, int, int, int]:
    w, h = min(w, img.width), min(h, img.height)
    left = min(max(cx - w / 2, 0), img.width - w)
    top = min(max(cy - h / 2, 0), img.height - h)
    return int(left), int(top), int(left + w), int(top + h)


def smart_crop(img: Image.Image, role: str, faces: list | None = None) -> Image.Image:
    """Square, face-centred crop for bride/groom; 4:3 crop keeping every face for the family photo."""
    faces = detect_faces(img) if faces is None else faces
    if role == "family":
        ratio = 4 / 3
        if faces:
            x0 = min(f[0] for f in faces); y0 = min(f[1] for f in faces)
            x1 = max(f[0] + f[2] for f in faces); y1 = max(f[1] + f[3] for f in faces)
            face_h = sum(f[3] for f in faces) / len(faces)
            x0, x1 = x0 - face_h, x1 + face_h
            y0, y1 = y0 - face_h * 0.8, y1 + face_h * 1.6  # room above heads, shoulders below
            need_w, need_h = x1 - x0, y1 - y0
            w, h = (need_h * ratio, need_h) if need_w / need_h < ratio else (need_w, need_w / ratio)
            if w > img.width or h > img.height:
                fit = min(img.width / w, img.height / h)
                if w * fit >= min(need_w, img.width) and h * fit >= min(need_h, img.height):
                    w, h = w * fit, h * fit  # still 4:3 and every face fits
                else:
                    w, h = min(w, img.width), min(h, img.height)  # keep every face; ratio gives way
            return img.crop(_clamp_box((x0 + x1) / 2, (y0 + y1) / 2, w, h, img))
        w = min(img.width, img.height * ratio)
        h = w / ratio
        return img.crop(_clamp_box(img.width / 2, h / 2 + max(0, (img.height - h) * 0.25), w, h, img))

    if faces:
        x, y, w, h = faces[0]
        side = min(max(max(w, h) * 3.2, min(img.size) * 0.6), img.width, img.height)  # head & shoulders
        return img.crop(_clamp_box(x + w / 2, y + h / 2 + h * 0.35, side, side, img))  # face in the upper-middle
    side = min(img.size)
    top_bias = (img.height - side) * 0.2  # portraits usually have the face near the top
    return img.crop(_clamp_box(img.width / 2, side / 2 + top_bias, side, side, img))


def studio_finish(img: Image.Image, role: str) -> Image.Image:
    img = img.convert("RGB")
    # Gentle grey-world white balance (half strength, clamped) removes yellow/blue casts.
    means = ImageStat.Stat(img).mean
    grey = sum(means) / 3
    factors = [min(max(1 + ((grey / max(m, 1)) - 1) * 0.5, 0.88), 1.12) for m in means]
    img = Image.merge("RGB", [ch.point(lambda v, f=f: min(255, int(v * f))) for ch, f in zip(img.split(), factors)])
    img = ImageOps.autocontrast(img, cutoff=(0.5, 0.5))
    lum = ImageStat.Stat(img.convert("L")).mean[0] / 255
    if lum < 0.45:  # lift dull or dark photos
        img = ImageEnhance.Brightness(img).enhance(min(1.0 + (0.45 - lum) * 1.2, 1.3))
    img = ImageEnhance.Color(img).enhance(1.12)
    r, g, b = img.split()  # warm wedding tone
    img = Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.03))), g, b.point(lambda v: int(v * 0.97))))
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=3))
    glow = ImageChops.screen(img, img.filter(ImageFilter.GaussianBlur(max(img.size) / 90)))
    img = Image.blend(img, glow, 0.14)
    if role == "family":  # soft vignette draws the eye to the people
        mask = Image.new("L", img.size, 0)
        from PIL import ImageDraw

        ImageDraw.Draw(mask).ellipse([-img.width * 0.15, -img.height * 0.15, img.width * 1.15, img.height * 1.15], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(img.size) / 8))
        img = Image.composite(img, ImageEnhance.Brightness(img).enhance(0.8), mask)
    return img


def ai_retouch(img: Image.Image) -> Image.Image:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(
        model=settings.gemini_image_model, contents=[AI_PROMPT, img],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            if part.inline_data and part.inline_data.data:
                out = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                return ImageOps.fit(out, img.size, Image.LANCZOS)
    raise RuntimeError("Gemini returned no image")


def enhance(data: bytes, role: str, use_ai: bool = False) -> tuple[bytes, dict]:
    """Returns (JPEG bytes, info). info: faces found, whether AI was used, any AI error."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((2400, 2400))
    faces = detect_faces(img)
    info = {"faces": len(faces), "ai": False}
    if use_ai and settings.gemini_enabled:
        try:
            retouched = ai_retouch(img)
            if not faces or detect_faces(retouched):  # never accept an AI result that lost the face
                img, info["ai"] = retouched, True
                faces = detect_faces(img) if faces else faces
            else:
                info["ai_error"] = "AI result rejected: face not found afterwards"
        except Exception as exc:  # noqa: BLE001 — fall back to the free studio finish
            log.warning("AI photo retouch failed: %s", exc)
            info["ai_error"] = str(exc)[:200]
    img = studio_finish(smart_crop(img, role, faces), role)
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue(), info


def ai_upgrade_portraits(order_id: int) -> None:
    """Background job: AI-retouch this order's enhanced photos (Gemini), recording the cost."""
    import secrets

    from app.db import SessionLocal
    from app.models import Asset, CostEntry, Order, utcnow
    from app.services.storage import storage

    if not settings.gemini_enabled:
        return
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if order is None:
            return
        raws = {a.card_key: a for a in order.live_assets("portrait_raw")}
        for shown in order.live_assets("portrait"):
            meta = shown.meta or {}
            raw = raws.get(shown.card_key)
            if raw is None or not meta.get("enhanced") or meta.get("ai") or meta.get("ai_error"):
                continue
            data, info = enhance(storage.read(raw.path), shown.card_key, use_ai=True)
            db.add(CostEntry(order_id=order.id, service="gemini_photo_retouch", units=1, cost_inr=settings.image_cost_inr))
            if not info.get("ai"):
                shown.meta = {**meta, "ai_error": info.get("ai_error", "unknown")}
                continue
            path = storage.save(f"orders/{order.public_id}/portraits/{shown.card_key}_{secrets.token_hex(4)}_ai.jpg", data)
            shown.deleted_at = utcnow()
            db.add(Asset(order_id=order.id, kind="portrait", card_key=shown.card_key, path=path,
                         content_type="image/jpeg", meta={"enhanced": True, **info}))
        db.commit()
