"""Brand images for the social pages: profile picture, covers for Facebook / YouTube / X, and launch posts.

Run from the project folder:  .venv/Scripts/python marketing/make_assets.py
Sample cards in marketing/src come from the live site (it renders Indian scripts correctly).
Text drawn here is English only, because Windows lacks the shaping library Indian scripts need."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
SRC, OUT = ROOT / "src", ROOT / "assets"
FONTS = ROOT.parent / "app" / "assets" / "fonts"
MAROON, DARK, GOLD, SOFT, CREAM = (122, 26, 43), (77, 15, 27), (201, 154, 60), (234, 215, 166), (255, 248, 236)
SITE = "invite-all.com"


def font(name: str, size: int, weight: str = "") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
    return f


def cinzel(size, weight="Bold"):
    return font("Cinzel.ttf", size, weight)


def serif(size, weight="SemiBold"):
    return font("CormorantGaramond.ttf", size, weight)


def script(size):
    return font("GreatVibes-Regular.ttf", size)


def background(w: int, h: int) -> Image.Image:
    """Deep maroon, lighter at the top, with a fine gold double frame."""
    img = Image.new("RGB", (w, h), DARK)
    top = Image.new("RGB", (w, h), (141, 35, 53))
    mask = Image.linear_gradient("L").rotate(180).resize((w, h))
    img = Image.composite(top, img, mask)
    d = ImageDraw.Draw(img)
    m = max(14, min(w, h) // 40)
    d.rectangle([m, m, w - m, h - m], outline=GOLD, width=max(2, m // 5))
    d.rectangle([m + m // 2, m + m // 2, w - m - m // 2, h - m - m // 2], outline=(150, 112, 50), width=1)
    return img


def card(path: str, width: int, angle: float = 0) -> Image.Image:
    """A sample card with a soft shadow, optionally tilted, as an RGBA layer."""
    c = Image.open(SRC / path).convert("RGB")
    c = c.resize((width, int(width * c.height / c.width)), Image.LANCZOS)
    pad = width // 8
    layer = Image.new("RGBA", (c.width + pad * 2, c.height + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([pad, pad + pad // 3, pad + c.width, pad + c.height + pad // 3], fill=(0, 0, 0, 150))
    layer = Image.alpha_composite(layer, shadow.filter(ImageFilter.GaussianBlur(pad // 3)))
    layer.paste(c, (pad, pad))
    ImageDraw.Draw(layer).rectangle([pad, pad, pad + c.width - 1, pad + c.height - 1], outline=SOFT, width=max(2, width // 160))
    return layer.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else layer


def paste_center(base: Image.Image, layer: Image.Image, cx: int, cy: int) -> None:
    base.paste(layer, (cx - layer.width // 2, cy - layer.height // 2), layer)


def text(d: ImageDraw.ImageDraw, xy, s: str, f, fill=CREAM, anchor="mm", max_w: int | None = None) -> None:
    if max_w:
        size = f.size
        while f.getlength(s) > max_w and size > 12:
            size -= 2
            f = f.font_variant(size=size)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def logo(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), MAROON)
    d = ImageDraw.Draw(img)
    r = size // 2
    d.ellipse([size * .06, size * .06, size * .94, size * .94], outline=GOLD, width=max(3, size // 60))
    d.ellipse([size * .1, size * .1, size * .9, size * .9], outline=(150, 112, 50), width=max(1, size // 300))
    text(d, (r, int(r * .92)), "IA", cinzel(int(size * .36)), fill=(240, 205, 120))
    text(d, (r, int(size * .7)), "INVITE ALL", cinzel(int(size * .07)), fill=SOFT)
    return img


def fan(base, files, cx, cy, width, spread):
    for path, angle, dx in zip(files, (8, -8, 0), (-spread, spread, 0)):
        paste_center(base, card(path, width, angle), cx + dx, cy + (0 if angle == 0 else width // 14))


def post(name: str, kicker: str, title: str, sub: str, draw_cards, footer="Free to create · Hindi & 9 languages") -> None:
    W, H = 1080, 1350
    img = background(W, H)
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 110), kicker, serif(40), fill=SOFT, max_w=900)
    # Cinzel has no ₹ sign; Cormorant does
    text(d, (W // 2, 190), title, serif(74, "Bold") if "₹" in title else cinzel(62), fill=(240, 205, 120), max_w=960)
    if sub:
        text(d, (W // 2, 262), sub, script(64), fill=CREAM, max_w=960)
    draw_cards(img)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([170, H - 170, W - 170, H - 92], radius=39, fill=GOLD)
    text(d, (W // 2, H - 131), f"Create yours free  →  {SITE}", serif(40, "Bold"), fill=DARK, max_w=700)
    text(d, (W // 2, H - 52), footer, serif(30), fill=SOFT)
    img.save(OUT / f"{name}.png", optimize=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    logo(1080).save(OUT / "profile_picture_1080.png")

    # Facebook cover 1640×624 (phones crop the sides: keep everything in the middle 1240)
    W, H = 1640, 624
    img = background(W, H)
    d = ImageDraw.Draw(img)
    text(d, (540, 190), "Invite All", script(150), fill=(240, 205, 120))
    text(d, (540, 320), "INVITATION CARDS FOR EVERY OCCASION", cinzel(38), fill=CREAM, max_w=660)
    text(d, (540, 390), "Wedding · Birthday · Griha Pravesh · Puja · Anniversary", serif(36), fill=SOFT, max_w=660)
    text(d, (540, 460), f"Free · Hindi & 9 languages · {SITE}", serif(36, "Bold"), fill=(240, 205, 120), max_w=660)
    fan(img, ["ev_kids_birthday.jpg", "ev_griha_pravesh.jpg", "en_card.png"], 1200, 320, 240, 130)
    img.save(OUT / "facebook_cover_1640x624.png", optimize=True)

    # X / Twitter header 1500×500
    W, H = 1500, 500
    img = background(W, H)
    d = ImageDraw.Draw(img)
    text(d, (560, 150), "Invite All", script(130), fill=(240, 205, 120))
    text(d, (560, 265), "INVITATION CARDS FOR EVERY OCCASION", cinzel(34), fill=CREAM, max_w=760)
    text(d, (560, 330), f"Free · in your language · {SITE}", serif(36, "Bold"), fill=SOFT, max_w=760)
    fan(img, ["ev_wedding_anniversary.jpg", "ev_satyanarayan_puja.jpg", "en_card.png"], 1150, 260, 200, 115)
    img.save(OUT / "x_header_1500x500.png", optimize=True)

    # YouTube banner 2560×1440: TVs show it all, phones only the middle 1546×423
    W, H = 2560, 1440
    img = background(W, H)
    d = ImageDraw.Draw(img)
    for i, f in enumerate(["st_south_indian.jpg", "ev_kids_birthday.jpg", "ev_baby_shower.jpg", "ev_grand_opening.jpg"]):
        paste_center(img, card(f, 300, (-6, 5, -4, 7)[i]), (260, 560, 2000, 2300)[i], (300, 1150, 1150, 300)[i])
    text(d, (W // 2 - 260, 630), "Invite All", script(170), fill=(240, 205, 120))
    text(d, (W // 2 - 260, 770), "INVITATION CARDS FOR EVERY OCCASION", cinzel(44), fill=CREAM, max_w=980)
    text(d, (W // 2 - 260, 850), f"Free · Hindi & 9 languages · {SITE}", serif(46, "Bold"), fill=SOFT, max_w=980)
    paste_center(img, card("en_personal.jpg", 250, 4), W // 2 + 580, 720)
    img.save(OUT / "youtube_banner_2560x1440.png", optimize=True)

    post("post1_launch", "Introducing", "Invite All", "your invitation, ready in 60 seconds",
         lambda im: fan(im, ["ev_kids_birthday.jpg", "ev_griha_pravesh.jpg", "en_card.png"], 540, 690, 470, 210))
    post("post2_personal_cards", "New", "Every guest gets their own card", "with their name on it",
         lambda im: paste_center(im, card("en_personal.jpg", 640, -3), 540, 700),
         footer="Send on WhatsApp, Instagram, Telegram, SMS or email")
    post("post3_languages", "Shubh Vivah", "Your wedding card, in your language", "Hindi · Marathi · Tamil · Telugu & more",
         lambda im: paste_center(im, card("hindi_card.png", 620, 3), 540, 700),
         footer="English + 9 Indian languages, every matra correct")
    post("post4_puja", "Griha Pravesh · Satyanarayan · Diwali", "Puja invitations in 60 seconds", "with a Shri Ganesh blessing",
         lambda im: fan(im, ["ev_satyanarayan_puja.jpg", "ev_diwali_puja.jpg", "ev_griha_pravesh.jpg"], 540, 700, 470, 200))

    def grid(im):
        files = ["ev_kids_birthday.jpg", "ev_wedding_anniversary.jpg", "ev_baby_shower.jpg",
                 "st_muslim_nikah.jpg", "ev_grand_opening.jpg", "ev_griha_pravesh.jpg"]
        for i, f in enumerate(files):
            paste_center(im, card(f, 270), 220 + (i % 3) * 320, 520 + (i // 3) * 400)
    post("post5_occasions", "Birthday · Anniversary · Baby shower · Nikah · Opening", "27 occasions, one free app", "", grid)

    def steps(im):
        d = ImageDraw.Draw(im)
        for i, (head, line) in enumerate([("Pick a design", "and your language"), ("Type names & date", "see the card change as you type"),
                                          ("Share it", "WhatsApp · Instagram · PDF · invite page")]):
            y = 400 + i * 230
            d.ellipse([140, y - 60, 260, y + 60], fill=GOLD)
            text(d, (200, y), str(i + 1), cinzel(70), fill=DARK)
            text(d, (300, y - 28), head, cinzel(50), fill=(240, 205, 120), anchor="lm")
            text(d, (300, y + 34), line, serif(40), fill=CREAM, anchor="lm", max_w=700)
    post("post6_how_it_works", "How it works", "3 steps. 60 seconds.", "no designer needed", steps)

    post("post7_price", "Made for every budget", "Free download. Full HD ₹9", "4K print-ready ₹99",
         lambda im: fan(im, ["st_north_indian.jpg", "st_south_indian.jpg", "en_card.png"], 540, 700, 470, 210),
         footer="Pay by UPI · No sign-up needed")

    # seasonal posts (CONTENT_CALENDAR.md)
    post("post8_wedding_season", "Shaadi season is here", "Your wedding card, every function", "free to make, ready in a minute",
         lambda im: fan(im, ["st_south_indian.jpg", "st_muslim_nikah.jpg", "en_card.png"], 540, 700, 470, 210),
         footer="Haldi · Mehndi · Sangeet · Wedding · Reception")
    post("post9_christmas", "Hosting this year?", "Christmas & New Year party invites", "food, music & a gift exchange",
         lambda im: fan(im, ["ev_kitty_party.jpg", "ev_family_reunion.jpg", "ev_christmas_newyear.jpg"], 540, 700, 470, 210))
    post("post10_lohri", "Lohri di lakh lakh vadhaiyan", "Lohri & Sankranti invitations", "bonfire, rewri & bhangra",
         lambda im: paste_center(im, card("ev_lohri_sankranti.jpg", 620, -3), 540, 700))

    def wording_post(im):
        d = ImageDraw.Draw(im)
        notes = [("Griha Pravesh", "New home, new beginnings! Join us for"), ("Wedding", "Together with their families…"),
                 ("Birthday", "It's party time! Please join us as"), ("Satyanarayan Puja", "With the blessings of the Almighty…")]
        for i, (head, line) in enumerate(notes):
            x, y = 110 + (i % 2) * 450, 390 + (i // 2) * 330
            d.rounded_rectangle([x, y, x + 410, y + 280], radius=24, fill=CREAM)
            text(d, (x + 205, y + 60), head, cinzel(34), fill=MAROON, max_w=370)
            text(d, (x + 205, y + 130), line, serif(30, "Medium"), fill=(70, 50, 45), max_w=370)
            d.rounded_rectangle([x + 105, y + 190, x + 305, y + 244], radius=27, fill=GOLD)
            text(d, (x + 205, y + 217), "Copy", serif(30, "Bold"), fill=DARK)
    post("post11_wording", "Need the right words?", "230 invitation messages", "Hindi & English · copy in one tap", wording_post,
         footer="invite-all.com/wording")

    # Story / reel cover 1080×1920 (leave the bottom free for Instagram's link sticker)
    W, H = 1080, 1920
    img = background(W, H)
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 220), "Type your names.", cinzel(70), fill=CREAM)
    text(d, (W // 2, 320), "See your card in 1 second.", script(96), fill=(240, 205, 120), max_w=960)
    paste_center(img, card("en_personal.jpg", 660, -3), W // 2, 950)
    text(d, (W // 2, 1560), f"Free at {SITE}", cinzel(60), fill=(240, 205, 120))
    text(d, (W // 2, 1640), "Wedding · Birthday · Puja · 27 occasions", serif(44), fill=SOFT)
    img.save(OUT / "story_launch_1080x1920.png", optimize=True)
    print("made", len(list(OUT.glob("*.png"))), "images in", OUT)


if __name__ == "__main__":
    main()
