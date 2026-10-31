"""Text overlay engine (C5).

AI image models misspell names, so the AI only paints the background and this module
typesets every word with real fonts: Great Vibes / Cinzel / Cormorant for English and
Noto Serif for Indian scripts. Text is auto-fitted into the card's text box.

Indian scripts need complex shaping (conjuncts, matras). Pillow does that through
libraqm, which needs the FriBiDi library at runtime — present in the Docker image
(`libfribidi0`). Without it, QC blocks cards that contain Indian-script text.
"""
import io
import platform
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from app.catalog import Style
from app.config import APP_DIR

CANVAS = (1080, 1350)
FONT_DIR = APP_DIR / "assets" / "fonts"
RAQM = features.check("raqm")

SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
}
SCRIPT_FONTS = {
    "devanagari": "NotoSerifDevanagari.ttf",
    "bengali": "NotoSerifBengali.ttf",
    "gurmukhi": "NotoSerifGurmukhi.ttf",
    "gujarati": "NotoSerifGujarati.ttf",
    "tamil": "NotoSerifTamil.ttf",
    "telugu": "NotoSerifTelugu.ttf",
    "kannada": "NotoSerifKannada.ttf",
    "malayalam": "NotoSerifMalayalam.ttf",
}
LATIN_FONTS = {"display": "GreatVibes-Regular.ttf", "heading": "Cinzel.ttf", "body": "CormorantGaramond.ttf"}
ROLE_FAMILY = {
    "headline": "heading",
    "title": "display",
    "names": "display",
    "connector": "display",
    "invite": "body",
    "family": "body",
    "date": "heading",
    "detail": "body",
    "small": "body",
}
ROLE_WEIGHT = {"headline": "Bold", "date": "Bold", "names": "Bold", "title": "Bold", "detail": "SemiBold", "invite": "Medium"}
_SYSTEM_FALLBACKS = (
    ["C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/georgia.ttf"]
    if platform.system() == "Windows"
    else ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]
)


@dataclass
class Line:
    text: str
    role: str  # see ROLE_FAMILY
    size: int
    color: str = "secondary"  # primary | secondary | accent
    max_lines: int = 1
    gap_before: int = 0


@dataclass
class Divider:
    gap_before: int = 14
    width: int = 280


@dataclass
class Layout:
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 where text may go
    photo_circle: tuple[int, int, int] | None = None  # cx, cy, r (offline generator only)


LAYOUT_PLAIN = Layout(box=(150, 250, 930, 1140))
LAYOUT_PHOTO = Layout(box=(150, 200, 930, 900), photo_circle=(540, 1110, 150))


@dataclass
class OverlayReport:
    scale: float = 1.0
    overflow: bool = False
    min_size_ok: bool = True
    text_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    rendered: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    shaping_ok: bool = True

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def detect_script(text: str) -> str:
    for ch in text:
        cp = ord(ch)
        for script, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                return script
    return "latin"


@lru_cache(maxsize=256)
def load_font(role: str, script: str, size: int) -> ImageFont.FreeTypeFont:
    family = ROLE_FAMILY[role]
    name = LATIN_FONTS[family] if script == "latin" else SCRIPT_FONTS[script]
    candidates = [FONT_DIR / name, *map(Path, _SYSTEM_FALLBACKS)]
    engine = ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC
    for path in candidates:
        if path.exists():
            font = ImageFont.truetype(str(path), size, layout_engine=engine)
            weight = ROLE_WEIGHT.get(role)
            if weight and path.parent == FONT_DIR:
                try:
                    font.set_variation_by_name(weight)
                except (OSError, ValueError):
                    pass  # static font or weight not offered
            return font
    return ImageFont.load_default(size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if font.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_line(line: Line, scale: float, width: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest font (≤ scaled size) where the text fits in `max_lines` lines."""
    script = detect_script(line.text)
    size = max(int(line.size * scale), 12)
    floor = max(int(line.size * 0.45), 12)
    while True:
        font = load_font(line.role, script, size)
        rows = _wrap(line.text, font, width) if line.max_lines > 1 else [line.text]
        if (len(rows) <= line.max_lines and all(font.getlength(r) <= width for r in rows)) or size <= floor:
            return font, rows, size
        size -= 2


def _row_height(font: ImageFont.FreeTypeFont, role: str) -> int:
    ascent, descent = font.getmetrics()
    factor = 0.9 if ROLE_FAMILY[role] == "display" else 1.12  # script fonts have tall empty ascenders
    return int((ascent + descent) * factor)


def _measure(items: list, scale: float, width: int):
    plan, total = [], 0
    for item in items:
        if isinstance(item, Divider):
            h = int(item.gap_before * scale) + 18
            plan.append((item, None, None, h))
        else:
            font, rows, size = _fit_line(item, scale, width)
            h = int(item.gap_before * scale) + _row_height(font, item.role) * len(rows)
            plan.append((item, font, rows, h))
        total += h
    return plan, total


def _luminance(rgb: tuple[int, ...]) -> float:
    def ch(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _draw_divider(draw: ImageDraw.ImageDraw, cx: int, y: int, width: int, color) -> None:
    half = width // 2
    draw.line([(cx - half, y), (cx - 14, y)], fill=color, width=2)
    draw.line([(cx + 14, y), (cx + half, y)], fill=color, width=2)
    draw.polygon([(cx, y - 8), (cx + 8, y), (cx, y + 8), (cx - 8, y)], fill=color)
    for dx in (-half - 6, half + 6):
        draw.ellipse([cx + dx - 3, y - 3, cx + dx + 3, y + 3], fill=color)


def compose_card(background: Image.Image, items: list, style: Style, layout: Layout) -> tuple[Image.Image, OverlayReport]:
    """Typeset `items` (Line / Divider) onto the background inside layout.box."""
    img = background.convert("RGBA").resize(CANVAS)
    x0, y0, x1, y1 = layout.box
    width, height = x1 - x0, y1 - y0
    report = OverlayReport()

    scale = 1.0
    plan, total = _measure(items, scale, width)
    while total > height and scale > 0.5:
        scale = round(scale - 0.04, 2)
        plan, total = _measure(items, scale, width)
    report.scale = scale
    report.overflow = total > height

    top = y0 + max((height - total) // 2, 0)
    cx = (x0 + x1) // 2
    colors = {"primary": style.text_primary, "secondary": style.text_secondary, "accent": style.accent}

    # Find the widest row so the backing panel hugs the text.
    widest = 0
    for item, font, rows, _ in plan:
        if font:
            widest = max(widest, *(int(font.getlength(r)) for r in rows))
        else:
            widest = max(widest, item.width)
    pad_x, pad_y = 56, 44
    panel_box = (cx - widest // 2 - pad_x, top - pad_y, cx + widest // 2 + pad_x, top + total + pad_y)
    panel_box = (max(panel_box[0], 70), max(panel_box[1], 70), min(panel_box[2], CANVAS[0] - 70), min(panel_box[3], CANVAS[1] - 70))
    report.text_bbox = panel_box

    panel = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(panel_box, radius=36, fill=style.panel)
    img = Image.alpha_composite(img, panel.filter(ImageFilter.GaussianBlur(10)))

    text_dark = _luminance(style.text_secondary) < 0.3
    shadow_rgba = (255, 255, 255, 170) if text_dark else (0, 0, 0, 150)
    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    text_layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    sdraw, tdraw = ImageDraw.Draw(shadow), ImageDraw.Draw(text_layer)

    y = top
    scripts = set()
    for item, font, rows, h in plan:
        if isinstance(item, Divider):
            yy = y + int(item.gap_before * scale) + 9
            _draw_divider(tdraw, cx, yy, int(item.width * min(scale + 0.1, 1)), style.accent)
            y += h
            continue
        y += int(item.gap_before * scale)
        scripts.add(detect_script(item.text))
        if font.size < 22 or font.size < item.size * 0.5:
            report.min_size_ok = False
        for row in rows:
            sdraw.text((cx + 2, y + 3), row, font=font, fill=shadow_rgba, anchor="ma")
            tdraw.text((cx, y), row, font=font, fill=colors[item.color], anchor="ma")
            y += _row_height(font, item.role)
        report.rendered.append(item.text)

    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(3)))
    img = Image.alpha_composite(img, text_layer)
    report.scripts = sorted(scripts)
    report.shaping_ok = RAQM or scripts <= {"latin"}
    return img.convert("RGB"), report


def add_qr(img: Image.Image, url: str, style: Style, label: str = "Scan to RSVP") -> Image.Image:
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    code = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((140, 140), Image.NEAREST)
    img = img.copy()
    draw = ImageDraw.Draw(img)
    x, y = CANVAS[0] - 140 - 96, CANVAS[1] - 140 - 120
    draw.rounded_rectangle([x - 10, y - 10, x + 150, y + 180], radius=14, fill=(255, 255, 255))
    img.paste(code, (x, y))
    draw.text((x + 70, y + 146), label, font=load_font("detail", "latin", 22), fill=(40, 30, 30), anchor="ma")
    return img


def watermark(img: Image.Image, text: str) -> Image.Image:
    """Diagonal 'PROOF' marks + lower resolution so proofs can't be used as finals."""
    base = img.convert("RGBA")
    tile = Image.new("RGBA", (CANVAS[0] * 2, CANVAS[1] * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    font = load_font("headline", "latin", 46)
    for row, yy in enumerate(range(0, tile.height, 190)):
        offset = (row % 2) * 260
        for xx in range(-offset, tile.width, 560):
            draw.text((xx, yy), text, font=font, fill=(255, 255, 255, 70), stroke_width=2, stroke_fill=(0, 0, 0, 50))
    tile = tile.rotate(30, resample=Image.BICUBIC)
    left, top = (tile.width - CANVAS[0]) // 2, (tile.height - CANVAS[1]) // 2
    base = Image.alpha_composite(base, tile.crop((left, top, left + CANVAS[0], top + CANVAS[1])))
    return base.convert("RGB").resize((720, 900), Image.LANCZOS)


def to_bytes(img: Image.Image, fmt: str = "PNG", quality: int = 90) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
