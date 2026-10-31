"""Image generation service (C3).

`GeminiGenerator` calls Google's Gemini image model. `OfflineGenerator` paints a
decorative background with Pillow so the whole business flow works with no API key
(local development, tests, demos and sample images).
"""
import io
import logging
import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.catalog import Style
from app.config import settings
from app.services.overlay import CANVAS, Layout

log = logging.getLogger(__name__)


@dataclass
class GenResult:
    image: Image.Image
    provider: str
    cost_inr: float = 0.0
    meta: dict = field(default_factory=dict)


class GenerationError(RuntimeError):
    pass


def _fit_cover(img: Image.Image, size=CANVAS) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS)


class GeminiGenerator:
    name = "gemini"

    def __init__(self) -> None:
        from google import genai

        self.client = genai.Client(api_key=settings.gemini_api_key)

    def generate(self, prompt: str, style: Style, layout: Layout, photos: list[Image.Image], seed: int) -> GenResult:
        from google.genai import types

        contents: list = [prompt, *photos]
        resp = self.client.models.generate_content(
            model=settings.gemini_image_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="4:5"),
            ),
        )
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if part.inline_data and part.inline_data.data:
                    img = Image.open(io.BytesIO(part.inline_data.data))
                    return GenResult(_fit_cover(img), self.name, settings.image_cost_inr, {"model": settings.gemini_image_model})
        reason = resp.candidates[0].finish_reason if resp.candidates else "no candidates"
        raise GenerationError(f"Gemini returned no image ({reason})")


class OfflineGenerator:
    """Procedural ornamental backgrounds. Not as rich as AI art, but on-brand and free."""

    name = "offline"

    def generate(self, prompt: str, style: Style, layout: Layout, photos: list[Image.Image], seed: int) -> GenResult:
        rnd = random.Random(seed)
        w, h = CANVAS
        img = Image.new("RGB", CANVAS)
        px = ImageDraw.Draw(img)
        for y in range(h):  # vertical gradient
            t = y / (h - 1)
            px.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(style.bg_top, style.bg_bottom)))

        layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        acc = style.accent
        faint, soft = (*acc, 38), (*acc, 120)

        for y in range(60, h, 64):  # lattice of tiny diamonds
            for x in range(60 + (y // 64 % 2) * 32, w, 64):
                d.polygon([(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)], fill=faint)

        d.rectangle([28, 28, w - 28, h - 28], outline=(*acc, 230), width=5)
        d.rectangle([46, 46, w - 46, h - 46], outline=soft, width=2)
        for cx, cy in [(46, 46), (w - 46, 46), (46, h - 46), (w - 46, h - 46)]:
            _mandala(d, cx, cy, 70, 12, acc, rnd)

        getattr(self, f"_motif_{style.motif}", self._motif_arch)(d, style, rnd)

        img = Image.alpha_composite(img.convert("RGBA"), layer)
        if photos and layout.photo_circle:
            img = _paste_photo(img, photos[0], layout.photo_circle, acc)
        return GenResult(img.convert("RGB"), self.name, 0.0, {"seed": seed})

    # --- motifs -----------------------------------------------------------
    def _motif_arch(self, d, s, rnd):
        w = CANVAS[0]
        d.arc([140, 70, w - 140, 520], 180, 360, fill=(*s.accent, 220), width=6)
        d.arc([170, 100, w - 170, 520], 180, 360, fill=(*s.accent, 120), width=2)
        _toran(d, 90, w - 90, 80, (242, 160, 30), rnd)
        _diyas(d, CANVAS[1] - 110, s.accent)

    def _motif_temple(self, d, s, rnd):
        w = CANVAS[0]
        cx = w // 2
        for i, (half, top) in enumerate([(200, 210), (160, 170), (120, 132), (80, 96), (44, 62)]):
            d.rectangle([cx - half, top, cx + half, top + 40], outline=(*s.accent, 210 - i * 20), width=3)
        d.polygon([(cx - 26, 62), (cx, 22), (cx + 26, 62)], fill=(*s.accent, 220))
        for side in (90, w - 90):  # banana leaf columns
            for y in range(320, 1180, 70):
                d.ellipse([side - 22, y, side + 22, y + 60], outline=(120, 200, 110, 140), width=3)
        _diyas(d, CANVAS[1] - 110, s.accent)

    def _motif_alpana(self, d, s, rnd):
        w, h = CANVAS
        _mandala(d, w // 2, 150, 120, 16, s.accent, rnd)
        _mandala(d, w // 2, h - 150, 100, 14, s.accent, rnd)
        for y in range(260, h - 260, 90):
            for x in (95, w - 95):
                d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=(*s.accent, 150), width=3)

    def _motif_crescent(self, d, s, rnd):
        w, h = CANVAS
        cx = w // 2
        d.ellipse([cx - 50, 90, cx + 50, 190], fill=(*s.accent, 230))
        d.ellipse([cx - 22, 78, cx + 66, 178], fill=(*s.bg_top, 255))
        d.arc([150, 210, w - 150, 640], 180, 360, fill=(*s.accent, 200), width=5)
        for x in (150, w - 150):  # lanterns
            d.line([(x, 46), (x, 140)], fill=(*s.accent, 200), width=2)
            d.polygon([(x - 22, 140), (x + 22, 140), (x + 30, 190), (x, 230), (x - 30, 190)], outline=(*s.accent, 220), fill=(*s.accent, 60))
        for x in range(90, w - 60, 60):  # geometric band
            d.polygon([(x, h - 120), (x + 30, h - 150), (x + 60, h - 120), (x + 30, h - 90)], outline=(*s.accent, 150), width=2)

    def _motif_floral(self, d, s, rnd):
        w, h = CANVAS
        petals = [(236, 170, 170), (250, 214, 200), (210, 226, 196), (255, 238, 220)]
        for cx, cy in [(130, 130), (w - 130, 130), (130, h - 130), (w - 130, h - 130)]:
            for _ in range(7):
                x, y, r = cx + rnd.randint(-80, 80), cy + rnd.randint(-80, 80), rnd.randint(26, 52)
                col = rnd.choice(petals)
                d.ellipse([x - r, y - r, x + r, y + r], fill=(*col, 190))
                d.ellipse([x - r // 3, y - r // 3, x + r // 3, y + r // 3], fill=(*s.accent, 150))
        d.arc([200, 110, w - 200, 560], 180, 360, fill=(*s.accent, 200), width=3)

    def _motif_marigold(self, d, s, rnd):
        w, h = CANVAS
        for x in range(100, w - 80, 110):  # hanging garlands
            length = rnd.randint(4, 7)
            for i in range(length):
                y = 60 + i * 34
                col = (250, 140, 20) if i % 2 else (255, 196, 40)
                d.ellipse([x - 16, y - 16, x + 16, y + 16], fill=(*col, 240), outline=(170, 70, 0, 200))
            d.polygon([(x, 60 + length * 34), (x - 12, 90 + length * 34), (x + 12, 90 + length * 34)], fill=(60, 140, 40, 230))
        for _ in range(14):
            x, y, r = rnd.randint(80, w - 80), rnd.randint(h - 260, h - 90), rnd.randint(14, 34)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 210, 60, 110))

    def _motif_paisley(self, d, s, rnd):
        w, h = CANVAS
        for cx, cy, flip in [(160, 200, 1), (w - 160, 200, -1), (160, h - 200, 1), (w - 160, h - 200, -1)]:
            for k in range(4):
                r = 70 - k * 14
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*s.accent, 170 - k * 25), width=3)
            d.arc([cx - 20 * flip - 90, cy - 150, cx - 20 * flip + 90, cy + 20], 200, 340, fill=(*s.accent, 160), width=3)
        for x in range(120, w - 100, 120):  # tassels
            d.line([(x, 46), (x, 120)], fill=(236, 60, 140, 200), width=3)
            d.ellipse([x - 10, 116, x + 10, 136], fill=(240, 176, 64, 230))


def _mandala(d, cx, cy, r, petals, acc, rnd):
    for k in range(petals):
        a = 2 * math.pi * k / petals
        tip = (cx + r * math.cos(a), cy + r * math.sin(a))
        l = (cx + r * 0.42 * math.cos(a - 0.22), cy + r * 0.42 * math.sin(a - 0.22))
        rr = (cx + r * 0.42 * math.cos(a + 0.22), cy + r * 0.42 * math.sin(a + 0.22))
        d.polygon([(cx, cy), l, tip, rr], outline=(*acc, 170), fill=(*acc, 40))
    d.ellipse([cx - r * 0.25, cy - r * 0.25, cx + r * 0.25, cy + r * 0.25], outline=(*acc, 200), width=3)


def _toran(d, x0, x1, y, col, rnd):
    for x in range(x0, x1, 26):
        sag = int(28 * math.sin(math.pi * ((x - x0) % 240) / 240))
        d.ellipse([x - 13, y + sag - 13, x + 13, y + sag + 13], fill=(*col, 235), outline=(160, 70, 0, 200))
    for x in range(x0 + 120, x1, 240):
        d.polygon([(x, y + 40), (x - 14, y + 90), (x + 14, y + 90)], fill=(50, 130, 40, 230))


def _diyas(d, y, acc):
    for x in range(150, CANVAS[0] - 100, 130):
        d.chord([x - 34, y - 20, x + 34, y + 30], 0, 180, fill=(*acc, 230))
        d.polygon([(x, y - 46), (x - 10, y - 14), (x + 10, y - 14)], fill=(255, 190, 60, 240))
        d.ellipse([x - 5, y - 30, x + 5, y - 18], fill=(255, 245, 200, 255))


def _paste_photo(img: Image.Image, photo: Image.Image, circle, acc) -> Image.Image:
    cx, cy, r = circle
    face = ImageOps.fit(photo.convert("RGB"), (2 * r, 2 * r), Image.LANCZOS, centering=(0.5, 0.35))
    mask = Image.new("L", face.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12], fill=(*acc, 255))
    img = Image.alpha_composite(img, ring.filter(ImageFilter.GaussianBlur(1)))
    img.paste(face, (cx - r, cy - r), mask)
    return img


_offline = OfflineGenerator()
_gemini: GeminiGenerator | None = None


def get_generator():
    global _gemini
    if settings.gemini_enabled:
        if _gemini is None:
            _gemini = GeminiGenerator()
        return _gemini
    return _offline


def offline_generator() -> OfflineGenerator:
    return _offline
