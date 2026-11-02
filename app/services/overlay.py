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
# Bump when card text styling changes: cached samples and the live demos are redrawn (customers' cards are not).
# 2: names in a clear serif instead of script. 3–4: Lord Ganesha on Hindu cards.
CARD_DESIGN = 4
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
    "names": "body",  # names in a clear serif: script names were hard to read
    "brand": "heading",
    "connector": "display",
    "invite": "body",
    "family": "body",
    "date": "heading",
    "detail": "body",
    "small": "body",
}
ROLE_WEIGHT = {"brand": "Bold", "headline": "Bold", "date": "Bold", "names": "Bold", "title": "Bold", "detail": "SemiBold", "invite": "Medium"}
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
class Emblem:
    """A picture centred above the text, e.g. Lord Ganesha on Hindu invitations (assets/art/<name>.png)."""
    name: str = "ganesha"
    height: int = 150
    gap_before: int = 0


@lru_cache(maxsize=4)
def _emblem_art(name: str) -> Image.Image:
    return Image.open(APP_DIR / "assets" / "art" / f"{name}.png").convert("RGBA")


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


def _fit_line(line: Line, scale: float, width: int, k: float = 1.0) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest font (≤ scaled size) where the text fits in `max_lines` lines."""
    script = detect_script(line.text)
    size = max(int(line.size * scale * k), 12)
    floor = max(int(line.size * 0.45 * k), 12)
    step = max(2, int(2 * k))
    while True:
        font = load_font(line.role, script, size)
        rows = _wrap(line.text, font, width) if line.max_lines > 1 else [line.text]
        if (len(rows) <= line.max_lines and all(font.getlength(r) <= width for r in rows)) or size <= floor:
            return font, rows, size
        size -= step


def _row_height(font: ImageFont.FreeTypeFont, role: str) -> int:
    ascent, descent = font.getmetrics()
    factor = 0.9 if ROLE_FAMILY[role] == "display" else 1.12  # script fonts have tall empty ascenders
    return int((ascent + descent) * factor)


def _measure(items: list, scale: float, width: int, k: float = 1.0):
    plan, total = [], 0
    for item in items:
        if isinstance(item, Emblem):
            h = int(item.gap_before * scale * k) + int(item.height * scale * k)
            plan.append((item, None, None, h))
        elif isinstance(item, Divider):
            h = int(item.gap_before * scale * k) + int(18 * k)
            plan.append((item, None, None, h))
        else:
            font, rows, size = _fit_line(item, scale, width, k)
            h = int(item.gap_before * scale * k) + _row_height(font, item.role) * len(rows)
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


def _draw_divider(draw: ImageDraw.ImageDraw, cx: int, y: int, width: int, color, k: float = 1.0) -> None:
    half, gap, d, dot, lw = width // 2, int(14 * k), int(8 * k), max(int(3 * k), 2), max(int(2 * k), 1)
    draw.line([(cx - half, y), (cx - gap, y)], fill=color, width=lw)
    draw.line([(cx + gap, y), (cx + half, y)], fill=color, width=lw)
    draw.polygon([(cx, y - d), (cx + d, y), (cx, y + d), (cx - d, y)], fill=color)
    for dx in (-half - 2 * dot, half + 2 * dot):
        draw.ellipse([cx + dx - dot, y - dot, cx + dx + dot, y + dot], fill=color)


def _soft(layer: Image.Image, radius: float) -> Image.Image:
    """Gaussian blur done at base resolution: identical look at 4K, a fraction of the cost."""
    if layer.size == CANVAS:
        return layer.filter(ImageFilter.GaussianBlur(radius))
    small = layer.resize(CANVAS, Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius))
    return small.resize(layer.size, Image.BILINEAR)


def compose_card(background: Image.Image, items: list, style: Style, layout: Layout, k: float = 1.0) -> tuple[Image.Image, OverlayReport]:
    """Typeset `items` (Line / Divider) onto the background inside layout.box.

    k scales the output: 1 = 1080×1350, 2 ≈ 2K, 3.56 = 4K. Text is rendered natively at that size, so it stays sharp.
    """
    size = (round(CANVAS[0] * k), round(CANVAS[1] * k))
    img = background.convert("RGBA").resize(size, Image.LANCZOS)
    x0, y0, x1, y1 = (round(v * k) for v in layout.box)
    width, height = x1 - x0, y1 - y0
    report = OverlayReport()

    scale = 1.0
    plan, total = _measure(items, scale, width, k)
    while total > height and scale > 0.5:
        scale = round(scale - 0.04, 2)
        plan, total = _measure(items, scale, width, k)
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
        elif isinstance(item, Divider):
            widest = max(widest, int(item.width * k))
    pad_x, pad_y, margin = int(56 * k), int(44 * k), int(70 * k)
    panel_box = (cx - widest // 2 - pad_x, top - pad_y, cx + widest // 2 + pad_x, top + total + pad_y)
    panel_box = (max(panel_box[0], margin), max(panel_box[1], margin), min(panel_box[2], size[0] - margin), min(panel_box[3], size[1] - margin))
    report.text_bbox = panel_box

    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(panel_box, radius=int(36 * k), fill=style.panel)
    img = Image.alpha_composite(img, _soft(panel, 10))

    text_dark = _luminance(style.text_secondary) < 0.3
    shadow_rgba = (255, 255, 255, 170) if text_dark else (0, 0, 0, 150)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    text_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    sdraw, tdraw = ImageDraw.Draw(shadow), ImageDraw.Draw(text_layer)
    sx, sy = max(int(2 * k), 1), max(int(3 * k), 1)

    y = top
    scripts = set()
    for item, font, rows, h in plan:
        if isinstance(item, Emblem):
            # deep gold on light panels, bright gold on dark ones
            art = _emblem_art(f"{item.name}-dark" if text_dark else item.name)
            eh = int(item.height * scale * k)
            ew = int(art.width * eh / art.height)
            text_layer.alpha_composite(art.resize((ew, eh), Image.LANCZOS), (cx - ew // 2, y + int(item.gap_before * scale * k)))
            y += h
            continue
        if isinstance(item, Divider):
            yy = y + int(item.gap_before * scale * k) + int(9 * k)
            _draw_divider(tdraw, cx, yy, int(item.width * k * min(scale + 0.1, 1)), style.accent, k)
            y += h
            continue
        y += int(item.gap_before * scale * k)
        scripts.add(detect_script(item.text))
        if font.size < 22 * k or font.size < item.size * k * 0.5:
            report.min_size_ok = False
        for row in rows:
            sdraw.text((cx + sx, y + sy), row, font=font, fill=shadow_rgba, anchor="ma")
            tdraw.text((cx, y), row, font=font, fill=colors[item.color], anchor="ma")
            y += _row_height(font, item.role)
        report.rendered.append(item.text)

    img = Image.alpha_composite(img, _soft(shadow, 3))
    img = Image.alpha_composite(img, text_layer)
    report.scripts = sorted(scripts)
    report.shaping_ok = RAQM or scripts <= {"latin"}
    return img.convert("RGB"), report


def add_qr(img: Image.Image, url: str, style: Style, label: str = "Scan to RSVP") -> Image.Image:
    k = img.width / CANVAS[0]
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    side = int(140 * k)
    code = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((side, side), Image.NEAREST)
    img = img.copy()
    draw = ImageDraw.Draw(img)
    x, y = img.width - side - int(96 * k), img.height - side - int(120 * k)
    pad = int(10 * k)
    draw.rounded_rectangle([x - pad, y - pad, x + side + pad, y + side + int(40 * k)], radius=int(14 * k), fill=(255, 255, 255))
    img.paste(code, (x, y))
    draw.text((x + side // 2, y + side + int(6 * k)), label, font=load_font("detail", "latin", int(22 * k)), fill=(40, 30, 30), anchor="ma")
    return img


def name_ribbon(img: Image.Image, kicker: str, name: str) -> Image.Image:
    """'Specially for / Sharma Family' on a cream ribbon in the empty band above the card's text
    (both layouts keep text below y=200 of 1350), for a guest's personal copy."""
    k = img.width / CANVAS[0]
    img = img.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    small = load_font("detail", detect_script(kicker), int(24 * k))
    max_w = int(780 * k)
    size = 46
    while True:  # shrink long names to fit one line
        big = load_font("headline", detect_script(name), int(size * k))
        if big.getlength(name) <= max_w - int(60 * k) or size <= 26:
            break
        size -= 2
    w = int(min(max(big.getlength(name), small.getlength(kicker)) + 70 * k, max_w))
    tall = 18 if detect_script(name) != "latin" or detect_script(kicker) != "latin" else 0
    h = int((size + 62 + tall) * k)  # Indian scripts: vowel signs above the line need more room
    cx, y = img.width // 2, int(52 * k)
    draw.rounded_rectangle([cx - w // 2, y, cx + w // 2, y + h], radius=int(22 * k), fill=(255, 250, 238, 235),
                           outline=(196, 152, 72, 255), width=max(int(3 * k), 1))
    draw.text((cx, y + int(10 * k)), kicker, font=small, fill=(138, 106, 58, 255), anchor="ma")
    draw.text((cx, y + h - int(14 * k)), name, font=big, fill=(110, 22, 32, 255), anchor="md")
    return Image.alpha_composite(img, layer).convert("RGB")


def credit_stamp(img: Image.Image, text: str) -> Image.Image:
    """Small, tasteful credit on the free Standard image (not a watermark over the design)."""
    img = img.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = load_font("detail", "latin", max(int(img.width * 0.022), 12))
    w = int(font.getlength(text))
    h = int(font.size * 1.6)
    x, y = (img.width - w) // 2, img.height - h - int(img.height * 0.012)
    draw.rounded_rectangle([x - h // 2, y, x + w + h // 2, y + h], radius=h // 2, fill=(255, 255, 255, 200))
    draw.text((img.width // 2, y + h // 2), text, font=font, fill=(90, 40, 40, 255), anchor="mm")
    return Image.alpha_composite(img, layer).convert("RGB")


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
