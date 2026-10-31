"""Illustrated (caricature-style) bride, groom and family portraits for the live demos.

Demos must never show real people without their permission, so these are drawn from
scratch as SVG, dressed for each region's wedding traditions, and rasterised with the
same headless Chrome used for the e-invite export.
"""
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

SKIN = {"fair": "#f3c9a8", "wheat": "#e2ad84", "warm": "#c98d63", "deep": "#a8714c"}
GOLD, GOLD_DARK = "#e7b54a", "#b07d1e"


@dataclass
class Person:
    gender: str  # f | m
    skin: str = "wheat"
    outfit: str = "#c0182f"
    border: str = GOLD
    head: str = "none"  # f: dupatta | shola | veil | jasmine | mundavalya ; m: safa | pheta | pagri | topor | none
    head_color: str = "#e8662a"
    beard: bool = False
    mustache: bool = True
    tilak: str = ""  # red | vibhuti | chandan
    nath: bool = True
    hair: str = "#2a1810"
    age: str = "young"  # young | elder | child
    glasses: bool = False
    bindi: bool = True  # bindi + sindoor (not for Christian brides)
    extras: dict = field(default_factory=dict)


def _face(p: Person, cx: float, cy: float, s: float) -> str:
    skin = SKIN[p.skin]
    elder = p.age == "elder"
    r = 118 * s
    out = []
    # neck
    out.append(f'<rect x="{cx - 34 * s}" y="{cy + 90 * s}" width="{68 * s}" height="{70 * s}" rx="{20 * s}" fill="{skin}"/>')
    # hair behind the head
    if p.gender == "f" and p.head not in ("veil",):
        out.append(f'<ellipse cx="{cx}" cy="{cy - 8 * s}" rx="{r * 1.12}" ry="{r * 1.18}" fill="{p.hair}"/>')
        if p.head in ("jasmine", "mundavalya", "dupatta", "shola"):
            out.append(f'<circle cx="{cx + r * 0.95}" cy="{cy + 10 * s}" r="{34 * s}" fill="{p.hair}"/>')  # bun
    # ears
    for side in (-1, 1):
        out.append(f'<ellipse cx="{cx + side * r * 0.98}" cy="{cy + 6 * s}" rx="{20 * s}" ry="{30 * s}" fill="{skin}"/>')
    # face
    out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * 1.12}" fill="{skin}"/>')
    # hair on top
    if p.gender == "f":
        hair_col = "#9b9b9b" if elder else p.hair
        out.append(f'<path d="M{cx - r * 0.98},{cy - 8 * s} Q{cx - r * 0.9},{cy - r * 1.2} {cx},{cy - r * 1.12} '
                   f'Q{cx + r * 0.9},{cy - r * 1.2} {cx + r * 0.98},{cy - 8 * s} Q{cx + r * 0.6},{cy - r * 0.75} {cx + 4 * s},{cy - r * 0.78} '
                   f'Q{cx - r * 0.6},{cy - r * 0.75} {cx - r * 0.98},{cy - 8 * s}Z" fill="{hair_col}"/>')
        if p.bindi and p.age != "child":
            out.append(f'<path d="M{cx},{cy - r * 1.1} L{cx},{cy - r * 0.78}" stroke="#c1272d" stroke-width="{5 * s}" stroke-linecap="round"/>')  # sindoor
    elif p.head == "none":
        hair_col = "#b5b5b5" if elder else p.hair
        out.append(f'<path d="M{cx - r * 0.98},{cy - 10 * s} Q{cx - r},{cy - r * 1.25} {cx},{cy - r * 1.18} '
                   f'Q{cx + r},{cy - r * 1.25} {cx + r * 0.98},{cy - 10 * s} Q{cx + r * 0.7},{cy - r * 0.8} {cx},{cy - r * 0.82} '
                   f'Q{cx - r * 0.7},{cy - r * 0.8} {cx - r * 0.98},{cy - 10 * s}Z" fill="{hair_col}"/>')
    # eyebrows + eyes (happy, slightly closed — classic caricature)
    for side in (-1, 1):
        ex = cx + side * 42 * s
        out.append(f'<path d="M{ex - 24 * s},{cy - 30 * s} Q{ex},{cy - 44 * s} {ex + 24 * s},{cy - 30 * s}" stroke="{p.hair if not elder else "#777"}" '
                   f'stroke-width="{7 * s}" fill="none" stroke-linecap="round"/>')
        out.append(f'<ellipse cx="{ex}" cy="{cy - 4 * s}" rx="{17 * s}" ry="{20 * s}" fill="#2b1a12"/>')
        out.append(f'<circle cx="{ex + 5 * s}" cy="{cy - 11 * s}" r="{6 * s}" fill="#fff"/>')
        if p.gender == "f":  # lashes + kajal flick
            out.append(f'<path d="M{ex + side * 14 * s},{cy - 16 * s} l{side * 12 * s},{-8 * s}" stroke="#2b1a12" stroke-width="{4 * s}" stroke-linecap="round"/>')
    if p.glasses:
        for side in (-1, 1):
            out.append(f'<circle cx="{cx + side * 42 * s}" cy="{cy - 4 * s}" r="{30 * s}" fill="none" stroke="#3a2a20" stroke-width="{5 * s}"/>')
        out.append(f'<path d="M{cx - 12 * s},{cy - 6 * s} L{cx + 12 * s},{cy - 6 * s}" stroke="#3a2a20" stroke-width="{5 * s}"/>')
    # cheeks
    for side in (-1, 1):
        out.append(f'<ellipse cx="{cx + side * 66 * s}" cy="{cy + 34 * s}" rx="{22 * s}" ry="{13 * s}" fill="#ff7a8a" opacity=".35"/>')
    # nose
    out.append(f'<path d="M{cx - 6 * s},{cy + 14 * s} Q{cx},{cy + 28 * s} {cx + 9 * s},{cy + 20 * s}" stroke="#8a4f33" stroke-width="{4 * s}" fill="none" stroke-linecap="round"/>')
    # smile
    lip = "#c2213a" if p.gender == "f" else "#8a3b2a"
    out.append(f'<path d="M{cx - 34 * s},{cy + 46 * s} Q{cx},{cy + 82 * s} {cx + 34 * s},{cy + 46 * s} Q{cx},{cy + 62 * s} {cx - 34 * s},{cy + 46 * s}Z" fill="{lip}"/>')
    if p.gender == "m" and p.mustache:
        out.append(f'<path d="M{cx - 40 * s},{cy + 42 * s} Q{cx - 18 * s},{cy + 28 * s} {cx},{cy + 38 * s} Q{cx + 18 * s},{cy + 28 * s} {cx + 40 * s},{cy + 42 * s} '
                   f'Q{cx + 18 * s},{cy + 36 * s} {cx},{cy + 44 * s} Q{cx - 18 * s},{cy + 36 * s} {cx - 40 * s},{cy + 42 * s}Z" fill="{"#8c8c8c" if elder else p.hair}"/>')
    if p.beard:
        out.append(f'<path d="M{cx - r * 0.92},{cy + 10 * s} Q{cx - r * 0.85},{cy + r * 1.35} {cx},{cy + r * 1.4} Q{cx + r * 0.85},{cy + r * 1.35} {cx + r * 0.92},{cy + 10 * s} '
                   f'Q{cx + r * 0.6},{cy + r * 0.85} {cx},{cy + r * 0.88} Q{cx - r * 0.6},{cy + r * 0.85} {cx - r * 0.92},{cy + 10 * s}Z" fill="{p.hair}"/>')
        out.append(f'<path d="M{cx - 30 * s},{cy + 52 * s} Q{cx},{cy + 76 * s} {cx + 30 * s},{cy + 52 * s}" stroke="#7a2a20" stroke-width="{6 * s}" fill="none" stroke-linecap="round"/>')
    # forehead marks
    if p.tilak == "red":
        out.append(f'<path d="M{cx},{cy - 62 * s} L{cx},{cy - 92 * s}" stroke="#d6262f" stroke-width="{9 * s}" stroke-linecap="round"/>')
    elif p.tilak == "vibhuti":
        for i in range(3):
            out.append(f'<path d="M{cx - 30 * s},{cy - (58 + i * 11) * s} L{cx + 30 * s},{cy - (58 + i * 11) * s}" stroke="#f4f0e6" stroke-width="{5 * s}" stroke-linecap="round"/>')
        out.append(f'<circle cx="{cx}" cy="{cy - 69 * s}" r="{6 * s}" fill="#d6262f"/>')
    elif p.gender == "f" and p.bindi:
        out.append(f'<circle cx="{cx}" cy="{cy - 54 * s}" r="{8 * s}" fill="#d6262f"/>')  # bindi
    if p.tilak == "chandan" or p.extras.get("chandan"):
        for i, a in enumerate(range(-60, 61, 20)):
            out.append(f'<circle cx="{cx + a * s}" cy="{cy - 64 * s - abs(a) * 0.35 * s}" r="{4.5 * s}" fill="#fff8ec"/>')
    # jewellery
    if p.gender == "f" and p.age != "child":
        for side in (-1, 1):  # jhumkas
            ex = cx + side * r * 1.0
            out.append(f'<circle cx="{ex}" cy="{cy + 40 * s}" r="{9 * s}" fill="{GOLD}"/>')
            out.append(f'<path d="M{ex - 16 * s},{cy + 70 * s} Q{ex},{cy + 40 * s} {ex + 16 * s},{cy + 70 * s}Z" fill="{GOLD}" stroke="{GOLD_DARK}" stroke-width="{2 * s}"/>')
            for k in (-10, 0, 10):
                out.append(f'<circle cx="{ex + k * s}" cy="{cy + 74 * s}" r="{3.5 * s}" fill="#fff3c4"/>')
        if p.nath and p.age == "young":
            out.append(f'<circle cx="{cx + 22 * s}" cy="{cy + 30 * s}" r="{17 * s}" fill="none" stroke="{GOLD}" stroke-width="{4 * s}"/>')
            out.append(f'<path d="M{cx + 38 * s},{cy + 28 * s} Q{cx + 80 * s},{cy + 10 * s} {cx + r * 0.98},{cy - 4 * s}" stroke="{GOLD}" stroke-width="{2.5 * s}" fill="none"/>')
    return "".join(out)


def _bride_head(p: Person, cx: float, cy: float, s: float) -> tuple[str, str]:
    """(behind-face layer, in-front layer) for the bride's headwear."""
    r = 118 * s
    behind, front = "", ""
    if p.head == "dupatta":
        behind = (f'<path d="M{cx - r * 1.45},{cy + r * 1.7} Q{cx - r * 1.55},{cy - r * 1.55} {cx},{cy - r * 1.5} '
                  f'Q{cx + r * 1.55},{cy - r * 1.55} {cx + r * 1.45},{cy + r * 1.7}Z" fill="{p.head_color}" opacity=".96"/>'
                  f'<path d="M{cx - r * 1.45},{cy + r * 1.7} Q{cx - r * 1.55},{cy - r * 1.55} {cx},{cy - r * 1.5} '
                  f'Q{cx + r * 1.55},{cy - r * 1.55} {cx + r * 1.45},{cy + r * 1.7}" fill="none" stroke="{GOLD}" stroke-width="{12 * s}" stroke-dasharray="{4 * s} {6 * s}"/>')
        front = _maang_tikka(cx, cy, s)
    elif p.head == "shola":  # Bengali shola topor: white crown + chandan
        front = (f'<path d="M{cx - r * 0.9},{cy - r * 0.95} Q{cx},{cy - r * 1.95} {cx + r * 0.9},{cy - r * 0.95} Q{cx},{cy - r * 1.15} {cx - r * 0.9},{cy - r * 0.95}Z" '
                 f'fill="#fffaf0" stroke="#e8d8b0" stroke-width="{3 * s}"/>'
                 + "".join(f'<circle cx="{cx + a * s}" cy="{cy - r * 1.25 - (60 - abs(a)) * 0.6 * s}" r="{7 * s}" fill="{GOLD}"/>' for a in range(-60, 61, 30)))
        behind = (f'<path d="M{cx - r * 1.4},{cy + r * 1.7} Q{cx - r * 1.5},{cy - r * 1.3} {cx},{cy - r * 1.25} Q{cx + r * 1.5},{cy - r * 1.3} {cx + r * 1.4},{cy + r * 1.7}Z" '
                  f'fill="{p.head_color}" opacity=".95"/>')
    elif p.head == "veil":  # Christian bride: white veil + flower crown
        behind = (f'<path d="M{cx - r * 1.5},{cy + r * 1.9} Q{cx - r * 1.6},{cy - r * 1.5} {cx},{cy - r * 1.45} Q{cx + r * 1.6},{cy - r * 1.5} {cx + r * 1.5},{cy + r * 1.9}Z" '
                  f'fill="#ffffff" opacity=".85"/>'
                  f'<ellipse cx="{cx}" cy="{cy - 8 * s}" rx="{r * 1.1}" ry="{r * 1.15}" fill="{p.hair}"/>')
        front = "".join(f'<circle cx="{cx + a * s}" cy="{cy - r * 1.02 + abs(a) * 0.28 * s}" r="{14 * s}" fill="{c}"/>'
                        for a, c in zip(range(-100, 101, 25), ["#fff", "#ffd1dc", "#fff", "#ffe3a3", "#fff", "#ffd1dc", "#fff", "#ffe3a3", "#fff"]))
    elif p.head == "jasmine":  # South Indian: jasmine strands + nethi chutti
        front = _maang_tikka(cx, cy, s, south=True)
        behind = "".join(f'<circle cx="{cx + r * 1.05 + (i % 2) * 8 * s}" cy="{cy - 30 * s + i * 22 * s}" r="{10 * s}" fill="#fffef6" stroke="#e9e3c8" stroke-width="{1.5 * s}"/>' for i in range(9))
    elif p.head == "mundavalya":  # Marathi: pearl strings on the forehead
        front = "".join(f'<path d="M{cx + a * s},{cy - r * 0.86} L{cx + a * 1.25 * s},{cy + r * 0.2}" stroke="#fff7e0" stroke-width="{4 * s}" stroke-dasharray="{2 * s} {7 * s}" stroke-linecap="round"/>'
                        for a in (-70, 70)) + f'<path d="M{cx - r * 0.85},{cy - r * 0.86} Q{cx},{cy - r * 1.02} {cx + r * 0.85},{cy - r * 0.86}" stroke="#fff7e0" stroke-width="{7 * s}" fill="none" stroke-dasharray="{2 * s} {8 * s}" stroke-linecap="round"/>'
    return behind, front


def _maang_tikka(cx: float, cy: float, s: float, south: bool = False) -> str:
    r = 118 * s
    pendant_y = cy - 66 * s
    out = f'<path d="M{cx},{cy - r * 1.08} L{cx},{pendant_y - 12 * s}" stroke="{GOLD}" stroke-width="{4 * s}"/>'
    if south:
        out += f'<path d="M{cx - r * 0.8},{cy - r * 0.8} Q{cx},{cy - r * 1.02} {cx + r * 0.8},{cy - r * 0.8}" stroke="{GOLD}" stroke-width="{5 * s}" fill="none"/>'
    out += (f'<circle cx="{cx}" cy="{pendant_y}" r="{14 * s}" fill="{GOLD}" stroke="{GOLD_DARK}" stroke-width="{2 * s}"/>'
            f'<circle cx="{cx}" cy="{pendant_y}" r="{6 * s}" fill="#d6262f"/>')
    return out


def _groom_head(p: Person, cx: float, cy: float, s: float) -> str:
    r = 118 * s
    c = p.head_color
    if p.head in ("safa", "pheta", "pagri"):
        top = cy - r * (1.55 if p.head == "pagri" else 1.45)
        out = (f'<path d="M{cx - r * 1.08},{cy - r * 0.45} Q{cx - r * 1.2},{top} {cx},{top - 10 * s} Q{cx + r * 1.2},{top} {cx + r * 1.08},{cy - r * 0.45} '
               f'Q{cx},{cy - r * 0.78} {cx - r * 1.08},{cy - r * 0.45}Z" fill="{c}"/>')
        for i in range(1, 4):  # wrap folds
            y = cy - r * 0.55 - i * r * 0.22
            out += f'<path d="M{cx - r * (1.04 - i * 0.07)},{y + 14 * s} Q{cx},{y - 18 * s} {cx + r * (1.04 - i * 0.07)},{y + 14 * s}" stroke="rgba(0,0,0,.18)" stroke-width="{5 * s}" fill="none"/>'
        if p.head == "safa":  # tail + kalgi brooch with feather
            out += f'<path d="M{cx + r * 0.95},{cy - r * 0.6} Q{cx + r * 1.6},{cy + r * 0.4} {cx + r * 1.25},{cy + r * 1.4}" stroke="{c}" stroke-width="{34 * s}" fill="none" stroke-linecap="round"/>'
        if p.head in ("safa", "pagri"):
            out += (f'<path d="M{cx},{top + 30 * s} Q{cx + 30 * s},{top - 70 * s} {cx + 6 * s},{top - 110 * s}" stroke="#fff4d6" stroke-width="{12 * s}" fill="none" stroke-linecap="round"/>'
                    f'<circle cx="{cx}" cy="{cy - r * 0.95}" r="{20 * s}" fill="{GOLD}" stroke="{GOLD_DARK}" stroke-width="{3 * s}"/>'
                    f'<circle cx="{cx}" cy="{cy - r * 0.95}" r="{8 * s}" fill="#1f8a5a"/>')
        if p.head == "pheta":  # Marathi pheta: pointed crest
            out += f'<path d="M{cx - 20 * s},{top + 10 * s} L{cx + 6 * s},{top - 70 * s} L{cx + 30 * s},{top + 14 * s}Z" fill="{c}"/>'
        return out
    if p.head == "topor":  # Bengali groom's tall white topor
        return (f'<path d="M{cx - r * 0.95},{cy - r * 0.62} L{cx},{cy - r * 2.5} L{cx + r * 0.95},{cy - r * 0.62} Q{cx},{cy - r * 0.85} {cx - r * 0.95},{cy - r * 0.62}Z" '
                f'fill="#fffaf0" stroke="#e8d8b0" stroke-width="{3 * s}"/>'
                + "".join(f'<path d="M{cx - r * (0.8 - i * 0.12)},{cy - r * (0.85 + i * 0.32)} L{cx + r * (0.8 - i * 0.12)},{cy - r * (0.85 + i * 0.32)}" stroke="{GOLD}" stroke-width="{5 * s}"/>' for i in range(4)))
    return ""


def _body(p: Person, cx: float, cy: float, s: float, bottom: float | None = None) -> str:
    """Shoulders and outfit below the face (down to `bottom` when given)."""
    top = cy + 140 * s
    w = 230 * s if p.age != "child" else 170 * s
    end = max(top + 260 * s, bottom or 0)
    out = (f'<path d="M{cx - w},{end} L{cx - w},{top + 120 * s} Q{cx - w},{top + 10 * s} {cx - 60 * s},{top} L{cx + 60 * s},{top} '
           f'Q{cx + w},{top + 10 * s} {cx + w},{top + 120 * s} L{cx + w},{end}Z" fill="{p.outfit}"/>')
    if p.gender == "f":  # blouse neckline + border
        out += (f'<path d="M{cx - 62 * s},{top} Q{cx},{top + 80 * s} {cx + 62 * s},{top}" fill="{SKIN[p.skin]}"/>'
                f'<path d="M{cx - w * 0.95},{top + 250 * s} Q{cx - w * 0.6},{top + 40 * s} {cx + w * 0.4},{top + 30 * s}" stroke="{p.border}" stroke-width="{22 * s}" fill="none"/>'
                f'<path d="M{cx - w * 0.95},{top + 250 * s} Q{cx - w * 0.6},{top + 40 * s} {cx + w * 0.4},{top + 30 * s}" stroke="{GOLD_DARK}" stroke-width="{4 * s}" fill="none" stroke-dasharray="{3 * s} {8 * s}"/>')
        if p.age != "child":  # gold choker + rani haar
            out += f'<path d="M{cx - 58 * s},{top - 6 * s} Q{cx},{top + 50 * s} {cx + 58 * s},{top - 6 * s}" stroke="{GOLD}" stroke-width="{12 * s}" fill="none"/>'
            out += "".join(f'<circle cx="{cx + a * s}" cy="{top + 20 * s + (50 - abs(a)) * 0.38 * s}" r="{6 * s}" fill="#d6262f"/>' for a in range(-40, 41, 20))
            out += f'<path d="M{cx - 80 * s},{top + 4 * s} Q{cx},{top + 130 * s} {cx + 80 * s},{top + 4 * s}" stroke="{GOLD}" stroke-width="{6 * s}" fill="none"/>'
    else:  # sherwani / kurta: placket + buttons, mala
        out += (f'<path d="M{cx - 50 * s},{top} L{cx},{top + 50 * s} L{cx + 50 * s},{top}" fill="{p.border}"/>'
                f'<path d="M{cx},{top + 50 * s} L{cx},{top + 260 * s}" stroke="{p.border}" stroke-width="{14 * s}"/>'
                + "".join(f'<circle cx="{cx}" cy="{top + (80 + i * 45) * s}" r="{7 * s}" fill="{GOLD}"/>' for i in range(4)))
        if p.extras.get("angavastram"):
            out += f'<path d="M{cx - w * 0.9},{top + 40 * s} Q{cx},{top + 120 * s} {cx + w * 0.95},{top + 250 * s}" stroke="{p.extras["angavastram"]}" stroke-width="{40 * s}" fill="none" opacity=".95"/>'
            out += f'<path d="M{cx - w * 0.9},{top + 40 * s} Q{cx},{top + 120 * s} {cx + w * 0.95},{top + 250 * s}" stroke="{GOLD}" stroke-width="{6 * s}" fill="none"/>'
        if p.extras.get("mala", p.age == "young"):
            out += "".join(f'<circle cx="{cx + a * s}" cy="{top + 30 * s + (90 - abs(a)) * 0.9 * s}" r="{8 * s}" fill="#fff8e8" stroke="#e7d9b0" stroke-width="{1.5 * s}"/>'
                           for a in range(-90, 91, 18))
        if p.extras.get("suit"):
            out += (f'<path d="M{cx - 70 * s},{top} L{cx - 10 * s},{top + 150 * s} L{cx - 90 * s},{top + 40 * s}Z" fill="#1d2433"/>'
                    f'<path d="M{cx + 70 * s},{top} L{cx + 10 * s},{top + 150 * s} L{cx + 90 * s},{top + 40 * s}Z" fill="#1d2433"/>'
                    f'<path d="M{cx},{top + 8 * s} l-{16 * s},{20 * s} l{16 * s},{14 * s} l{16 * s},-{14 * s}Z" fill="#7a1a2b"/>')
    return out


def person_svg(p: Person, cx: float, cy: float, s: float, bottom: float | None = None) -> str:
    behind = front = groom = ""
    if p.gender == "f":
        behind, front = _bride_head(p, cx, cy, s)
    else:
        groom = _groom_head(p, cx, cy, s)
    return behind + _body(p, cx, cy, s, bottom) + _face(p, cx, cy, s) + front + groom


def _backdrop(w: int, h: int, c1: str, c2: str, accent: str) -> str:
    petals = "".join(
        f'<circle cx="{x}" cy="{30 + (i % 2) * 14}" r="16" fill="{"#f6a21a" if i % 2 else "#ffcb3d"}"/>' for i, x in enumerate(range(20, w, 34))
    )
    return (f'<defs><radialGradient id="bg" cx="50%" cy="35%" r="75%"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></radialGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#bg)"/>'
            f'<circle cx="{w / 2}" cy="{h * 0.42}" r="{min(w, h) * 0.36}" fill="none" stroke="{accent}" stroke-width="3" opacity=".45"/>'
            f'<circle cx="{w / 2}" cy="{h * 0.42}" r="{min(w, h) * 0.42}" fill="none" stroke="{accent}" stroke-width="1.5" opacity=".3" stroke-dasharray="6 10"/>'
            + petals)


REGIONS: dict[str, dict] = {
    "north": dict(bride=Person("f", "wheat", "#b3122b", GOLD, "dupatta", "#d81e45"),
                  groom=Person("m", "wheat", "#f3e2c0", "#c99a3c", "safa", "#e8662a", tilak="red"),
                  bg=("#fff1d6", "#f3c46a")),
    "punjab": dict(bride=Person("f", "fair", "#d6336c", GOLD, "dupatta", "#f06595"),
                   groom=Person("m", "fair", "#f8eedb", "#c99a3c", "pagri", "#e64980", beard=True),
                   bg=("#ffe8f0", "#f7a8c4")),
    "bengal": dict(bride=Person("f", "wheat", "#c1121f", "#fff8ec", "shola", "#c1121f", extras={"chandan": True}),
                   groom=Person("m", "wheat", "#fffaf0", "#e8d8b0", "topor", tilak="chandan", extras={"mala": True}),
                   bg=("#fff4ec", "#f2b8a0")),
    "maha": dict(bride=Person("f", "warm", "#1f7a4d", GOLD, "mundavalya", nath=True),
                 groom=Person("m", "warm", "#fffaf0", "#e8662a", "pheta", "#f08c00", tilak="red"),
                 bg=("#f0fae8", "#a9dd8c")),
    "gujarat": dict(bride=Person("f", "wheat", "#fffaf0", "#c1121f", "dupatta", "#c1121f"),
                    groom=Person("m", "wheat", "#f7e7c6", "#9c2c2c", "safa", "#c2255c", tilak="red"),
                    bg=("#fff6e0", "#f5c86e")),
    "south": dict(bride=Person("f", "warm", "#a61e4d", GOLD, "jasmine", nath=False),
                  groom=Person("m", "warm", "#fffbf0", GOLD, "none", tilak="vibhuti",
                               extras={"angavastram": "#fffbf0", "mala": False}),
                  bg=("#effbf3", "#8fd1a8")),
    "kerala_christian": dict(bride=Person("f", "warm", "#fffdf8", "#e8d8a8", "veil", nath=False, bindi=False),
                             groom=Person("m", "warm", "#252c3d", "#ffffff", "none", mustache=True, extras={"suit": True, "mala": False}),
                             bg=("#f6f3ec", "#cfd8c6")),
}
LANG_REGION = {"en": "north", "hi": "north", "pa": "punjab", "bn": "bengal", "mr": "maha", "gu": "gujarat",
               "ta": "south", "te": "south", "kn": "south", "ml": "kerala_christian"}


def portrait_svg(region: str, role: str) -> tuple[str, int, int]:
    spec = REGIONS[region]
    c1, c2 = spec["bg"]
    if role in ("bride", "groom"):
        w = h = 900
        p = spec[role]
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                + _backdrop(w, h, c1, c2, GOLD_DARK) + person_svg(p, w / 2, 400, 1.55) + "</svg>"), w, h
    # family: parents either side, couple in the middle, little sibling in front
    w, h = 1400, 1000
    bride, groom = spec["bride"], spec["groom"]
    dad = replace(groom, age="elder", head="none" if groom.head in ("topor",) else groom.head, outfit="#e9dcc3",
                  border="#8a6a3a", glasses=True, extras={"mala": False}, tilak=groom.tilak, beard=groom.beard)
    mom = replace(bride, age="elder", head="dupatta" if bride.head != "veil" else "none", outfit="#7b2a8a",
                  head_color="#9b4fb0", nath=False, border=GOLD)
    kid = Person("m", groom.skin, "#2a6fdb", "#ffd43b", "none", age="child", mustache=False, extras={"mala": False})
    figures = [  # back row: parents at the sides, couple in the middle; little one in front
        (dad, 205, 450, 0.92), (mom, 1195, 470, 0.9), (groom, 560, 420, 1.0), (bride, 840, 440, 0.98), (kid, 700, 690, 0.72),
    ]
    body = "".join(person_svg(p, x, y, sc, bottom=h) for p, x, y, sc in figures)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            + _backdrop(w, h, c1, c2, GOLD_DARK) + body + "</svg>"), w, h


def render_png(svg: str, w: int, h: int) -> bytes | None:
    """Rasterise with headless Chrome. None if Chrome isn't available."""
    from app.services.export import chrome_binary

    chrome = chrome_binary()
    if not chrome:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp, "art.html")
        page.write_text(f'<!doctype html><html><body style="margin:0;background:#fff">{svg}</body></html>', encoding="utf-8")
        out = Path(tmp, "art.png")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                        f"--user-data-dir={Path(tmp, 'p')}", f"--window-size={w},{h}", "--force-device-scale-factor=1",
                        f"--screenshot={out}", page.as_uri()], capture_output=True, timeout=60)
        return out.read_bytes() if out.exists() else None


def couple_frame(bride_jpeg: bytes, groom_jpeg: bytes) -> bytes:
    """A royal double-arch frame of the bride's and groom's photos (4:3), studio-finished and vibrant."""
    import io

    from PIL import Image, ImageDraw, ImageFilter

    from app.services import photo_enhance as pe
    from app.services.overlay import load_font

    W, H, PW, PH = 1600, 1200, 600, 860

    def panel(data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        faces = pe.detect_faces(img)
        w = min(img.width, img.height * PW / PH)
        h = w * PH / PW
        cx = faces[0][0] + faces[0][2] / 2 if faces else img.width / 2
        top = (faces[0][1] - faces[0][3] * 0.9) if faces else 0
        left = min(max(cx - w / 2, 0), img.width - w)
        top = min(max(top, 0), img.height - h)
        crop = img.crop((int(left), int(top), int(left + w), int(top + h)))
        return pe.studio_finish(crop, "portrait", vibrant=True).resize((PW, PH), Image.LANCZOS)

    bride, groom = panel(bride_jpeg), panel(groom_jpeg)
    # Background: the two photos blurred into a warm glow
    bg = Image.new("RGB", (W, H))
    bg.paste(bride.resize((W // 2, H)), (0, 0))
    bg.paste(groom.resize((W // 2, H)), (W // 2, 0))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (90, 20, 30)), 0.45)
    canvas = bg.convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    def arch_mask(w: int, h: int) -> Image.Image:
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        d.rectangle([0, w // 2, w, h], fill=255)
        d.ellipse([0, 0, w, w], fill=255)
        return m

    for img, x in ((bride, 170), (groom, W - 170 - PW)):
        y = 220
        canvas.paste((231, 181, 74, 255), (x - 14, y - 14), arch_mask(PW + 28, PH + 28))  # gold arch border
        canvas.paste(img, (x, y), arch_mask(PW, PH))
    # Marigold garland across the top
    for i, gx in enumerate(range(30, W, 44)):
        sag = int(26 * abs(((gx % 400) - 200) / 200))
        col = (246, 162, 26, 255) if i % 2 else (255, 203, 61, 255)
        draw.ellipse([gx - 20, 50 + sag - 20, gx + 20, 50 + sag + 20], fill=col)
    font = load_font("names", "latin", 150)
    draw.text((W // 2, 640), "&", font=font, fill=(255, 226, 150, 255), anchor="mm")
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


# --- portraits for non-wedding demo events --------------------------------------
_CHILD_BOY = Person("m", "wheat", "#2a6fdb", "#ffd43b", "none", age="child", mustache=False, extras={"mala": False})
_CHILD_GIRL = Person("f", "fair", "#e64980", "#ffd43b", "none", age="child", nath=False, bindi=False)
_ELDER_MAN = Person("m", "wheat", "#7a1f2b", GOLD, "none", age="elder", glasses=True, extras={"mala": False})
_YOUNG_WOMAN = Person("f", "fair", "#7048e8", GOLD, "none", nath=False, bindi=False)
_SAREE_WOMAN = Person("f", "wheat", "#c2255c", GOLD, "dupatta", "#e64980", nath=False)
_KURTA_MAN = Person("m", "wheat", "#f3e2c0", "#c99a3c", "none", extras={"mala": False})
_BRAHMIN_BOY = Person("m", "warm", "#fff4d6", "#e8662a", "none", age="child", mustache=False, tilak="red", extras={"mala": False})

# event type -> (primary person, secondary person, family region or None)
EVENT_PORTRAITS = {
    "kids_birthday": (_CHILD_BOY, None, "north"),
    "milestone_birthday": (_ELDER_MAN, None, "north"),
    "theme_party": (_YOUNG_WOMAN, None, None),
    "wedding_anniversary": (_SAREE_WOMAN, _KURTA_MAN, "north"),
    "milestone_anniversary": (replace(_SAREE_WOMAN, age="elder"), replace(_KURTA_MAN, age="elder", glasses=True), "north"),
    "baby_shower": (_SAREE_WOMAN, _KURTA_MAN, "north"),
    "namakaran": (_CHILD_GIRL, None, "north"),
    "annaprashan": (_CHILD_BOY, None, "north"),
    "mundan": (_CHILD_BOY, None, "north"),
    "upanayanam": (_BRAHMIN_BOY, None, "south"),
    "kitty_party": (_YOUNG_WOMAN, None, None),
    "christmas_newyear": (None, None, "kerala_christian"),
}
for _key in ("satyanarayan_puja", "rudrabhishek", "ganesh_chaturthi", "griha_pravesh", "krishna_janmashtami",
             "durga_puja", "diwali_puja", "sundar_kand", "lohri_sankranti", "family_reunion"):
    EVENT_PORTRAITS[_key] = (None, None, "bengal" if _key == "durga_puja" else "punjab" if _key == "lohri_sankranti" else "north")


def event_portrait_svg(type_key: str, role: str, bg: tuple[str, str] = ("#fff1d6", "#f3c46a")) -> tuple[str, int, int] | None:
    """SVG for a demo event's bride (= main person), groom (= second person) or family slot, or None."""
    primary, secondary, family_region = EVENT_PORTRAITS.get(type_key, (None, None, None))
    if role == "family":
        return portrait_svg(family_region, "family") if family_region else None
    person = primary if role == "bride" else secondary
    if person is None:
        return None
    w = h = 900
    scale = 1.75 if person.age == "child" else 1.55
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            + _backdrop(w, h, bg[0], bg[1], GOLD_DARK) + person_svg(person, w / 2, 400, scale) + "</svg>"), w, h
