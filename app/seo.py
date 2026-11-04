"""Search landing pages: one page per thing people search for ("griha pravesh invitation card",
"hindi wedding card", "nikah invitation"…), each with its own title, description, wording samples,
tips and FAQ, linking into the free creator. Listed in the sitemap and the site footer."""
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app import events
from app.catalog import LANGUAGES, RESOLUTIONS, STYLES

SUFFIX = "invitation-card"

# Shorter, search-shaped URL names than the occasion's display name
TYPE_SLUGS = {
    "milestone_anniversary": "silver-golden-jubilee", "durga_puja": "navratri-durga-puja", "diwali_puja": "diwali-puja", "chhath_puja": "chhath-puja",
    "sundar_kand": "sundarkand-path", "baby_shower": "baby-shower-godh-bharai", "namakaran": "namkaran-naming-ceremony",
    "annaprashan": "annaprashan", "mundan": "mundan-ceremony", "upanayanam": "janeu-upanayanam",
    "christmas_newyear": "christmas-new-year-party", "grand_opening": "inauguration-opening-ceremony",
    "annual_day": "office-annual-day", "lohri_sankranti": "lohri-sankranti",
}
STYLE_PAGES = {  # wedding styles people search for by name
    "muslim_nikah": ("nikah", "Nikah Invitation Card", "Nikah", "निकाह"),
    "christian": ("christian-wedding", "Christian Wedding Invitation Card", "Christian wedding", "ईसाई विवाह"),
    "south_indian": ("south-indian-wedding", "South Indian Wedding Invitation Card", "South Indian wedding", "दक्षिण भारतीय विवाह"),
    "haldi": ("haldi-ceremony", "Haldi Ceremony Invitation Card", "Haldi ceremony", "हल्दी रस्म"),
    "mehndi": ("mehndi-ceremony", "Mehndi Ceremony Invitation Card", "Mehndi ceremony", "मेहंदी रस्म"),
}

TIPS = {
    "wedding": ["The couple's names, and the parents' names if you like (\"daughter of… / son of…\")",
                "Every function with its own date, time and venue: Haldi, Mehndi, Sangeet, Wedding, Reception",
                "The full venue address with a landmark, so the map link works",
                "A line of blessing or invocation (Shri Ganesh, Bismillah, or none)",
                "Who is inviting: \"The Sharma & Verma families\"",
                "Dress code, livestream link or shagun UPI if you want them"],
    "birthday": ["Whose birthday it is, and the age if it's a milestone (1st, 18th, 50th, 60th…)",
                 "Date, start time and an end time for kids' parties, so parents can plan pickup",
                 "Venue with a landmark; mention parking if it's a banquet hall",
                 "The theme or dress code (Superheroes, Bollywood Night, all-white…)",
                 "An RSVP so you can order the right amount of food and return gifts"],
    "anniversary": ["The couple's names and how many years (10th, Silver 25th, Golden 50th)",
                    "Who is hosting: the couple, or their children as a surprise",
                    "Date, time and venue, plus dinner or programme timings",
                    "A warm line about the years together",
                    "RSVP, and a gift note if you'd rather have blessings only"],
    "puja": ["The name of the puja or path and the deity",
             "The muhurat: date and start time, and when aarti and prasad or bhojan are",
             "The host family's name and full address with a landmark",
             "A Shri Ganesh invocation at the top (added for you)",
             "Whether it's family-only or open for neighbours and friends"],
    "baby": ["The ceremony (Godh Bharai, Namkaran, Annaprashan, Mundan, Janeu)",
             "The baby's or mother-to-be's name and the parents' names",
             "Date, muhurat time and venue",
             "Lunch or dinner timings after the ceremony",
             "A blessing line from the grandparents if you like"],
    "festival": ["The festival or party and who is hosting",
                 "Date, time and venue (or \"at our home\" with the address)",
                 "Theme or dress code (traditional, retro, ugly sweater…)",
                 "Food and programme: bonfire, dinner, games, gift exchange",
                 "An RSVP so you know how many are coming"],
    "corporate": ["The company or brand name, written exactly as on your logo",
                  "What the event is: inauguration, annual day, product launch",
                  "Chief guest or theme",
                  "Date, time, venue and parking or entry details",
                  "A contact person for RSVP"],
}


TYPE_TIPS = {
    "chhath-puja-invitation-card": [
        "The four days: Nahay Khay, Kharna, Sandhya Arghya and Usha Arghya, with dates",
        "The ghat or pond where the arghya will be offered, with a landmark, and the time of sunset and sunrise",
        "Where to gather first (your home) and when the family will leave for the ghat",
        "Kharna prasad timings (kheer, roti) and thekua prasad after the Usha Arghya",
        "Who is observing the vrat (the vratee), and the host family's name",
    ],
}


@dataclass(frozen=True)
class Landing:
    slug: str
    h1: str
    name: str  # "Griha Pravesh" (used inside sentences)
    local_name: str  # Hindi or regional name shown under the heading
    category: str
    create_url: str
    demo_url: str
    sample: str
    intro: str
    wording_en: list[str] = field(default_factory=list)
    wording_local: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        return f"/{self.slug}"

    @property
    def title(self) -> str:
        """Under ~60 characters so Google shows it whole: 'Free Griha Pravesh Invitation Card Maker | Invite All'."""
        short = re.sub(r"\s*\(.*?\)", "", self.h1).replace(" / ", " & ")
        return f"Free {short} Maker | Invite All"

    @property
    def description(self) -> str:
        return (f"Create a {self.name} invitation card online free in 60 seconds. Beautiful designs, Hindi and 9 Indian "
                f"languages, photos and a UPI gift QR. Download or share on WhatsApp.")

    @property
    def tips(self) -> list[str]:
        return TYPE_TIPS.get(self.slug) or TIPS[self.category]

    def faqs(self) -> list[tuple[str, str]]:
        hd = RESOLUTIONS["1080"]
        return [
            (f"Is the {self.name} invitation card maker free?",
             f"Yes. Creating the card and downloading the standard {RESOLUTIONS['free'].width}p version is free. Full HD "
             f"({hd.width}×{hd.height}) without the small credit is ₹{hd.price}, and 2K / 4K print sizes are also available."),
            (f"Can I make a {self.name} invitation in Hindi or another Indian language?",
             "Yes: English, Hindi, Marathi, Bengali, Gujarati, Punjabi, Tamil, Telugu, Kannada and Malayalam, with fonts "
             "that write every matra correctly."),
            (f"How do I send the {self.name} invitation on WhatsApp?",
             "Download the card or the complete e-invite PDF, or share your invite page link. You can also make a personal "
             "invite for each guest: their own card with their name on it, sent on WhatsApp, SMS, Telegram, Instagram, Facebook or email."),
            ("Can guests RSVP and get directions?",
             "Yes. With any paid size your invitation gets a live page with a countdown, a Google Maps button, add-to-calendar "
             "and RSVP, so you know exactly who is coming."),
            ("Can I add photos and a UPI QR for gifts?",
             "Yes. Add up to three photos (we frame and enhance them), and your UPI ID, UPI mobile number or payment QR so "
             "guests can send shagun or gifts."),
        ]


    def jsonld(self, base_url: str, brand: str) -> dict:
        """Breadcrumbs, FAQ and the free web app, for Google's rich results."""
        return {"@context": "https://schema.org", "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": brand, "item": f"{base_url}/"},
                {"@type": "ListItem", "position": 2, "name": "Occasions", "item": f"{base_url}/occasions"},
                {"@type": "ListItem", "position": 3, "name": self.h1, "item": f"{base_url}{self.path}"}]},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in self.faqs()]},
            {"@type": "WebApplication", "name": f"{self.h1} maker", "url": f"{base_url}{self.create_url}",
             "applicationCategory": "DesignApplication", "operatingSystem": "Any, in the browser",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"}},
        ]}


def _wording(t: events.EventType) -> tuple[list[str], list[str]]:
    primary, secondary, detail = t.demo
    names = f"{primary} & {secondary}" if secondary else primary
    en = [t.kicker, t.headline, names]
    hi = [t.kicker_hi, t.headline_hi, names]
    if detail:
        en.append(t.detail_fmt.format(detail=detail))
        hi.append(t.detail_fmt_hi.format(detail=detail))
    when = ["Sunday, 13 December 2026 · 11:00 AM", "Grand Banquet, MG Road, Pune"]
    return en + when, hi + ["रविवार, 13 दिसंबर 2026 · प्रातः 11:00 बजे", "ग्रैंड बैंक्वेट, एम.जी. रोड, पुणे"]


WEDDING_EN = ["Shri Ganeshaya Namah", "Together with their families", "Ananya", "daughter of Smt. & Shri Rakesh Sharma",
              "&", "Arjun", "son of Smt. & Shri Vinod Mishra", "request the pleasure of your company at their wedding",
              "Wednesday, 30 December 2026 · 7:30 PM", "Ganga Mahal, Assi Ghat, Varanasi"]
WEDDING_HI = ["॥ श्री गणेशाय नमः ॥", "शुभ विवाह", "आप सपरिवार सादर आमंत्रित हैं", "अनन्या", "सुपुत्री श्रीमती एवं श्री राकेश शर्मा",
              "संग", "अर्जुन", "सुपुत्र श्रीमती एवं श्री विनोद मिश्रा", "बुधवार, 30 दिसंबर 2026 · सायं 7:30 बजे",
              "गंगा महल, अस्सी घाट, वाराणसी"]


@lru_cache(maxsize=1)
def pages() -> dict[str, Landing]:
    found: list[Landing] = [Landing(
        f"wedding-{SUFFIX}", "Wedding Invitation Card", "wedding", "शादी का कार्ड · शुभ विवाह निमंत्रण", "wedding",
        "/create", "/demo/en", "/samples/north_indian.jpg",
        "Design a wedding card for the main ceremony and a matching card for every function: Haldi, Mehndi, Sangeet, "
        "Wedding and Reception. Guests get a cinematic invite page where palace doors open, petals fall and your music plays.",
        WEDDING_EN, WEDDING_HI)]
    for code, lang in LANGUAGES.items():
        if code == "en":
            continue
        style = "south_indian" if code in ("ta", "te", "kn", "ml") else "bengali" if code == "bn" else "north_indian"
        found.append(Landing(
            f"{lang.name.lower()}-wedding-{SUFFIX}", f"{lang.name} Wedding Invitation Card", f"{lang.name} wedding",
            f"{lang.native} · {lang.headline}", "wedding", f"/create?lang={code}&style={style}", f"/demo/{code}",
            f"/samples/{style}.jpg",
            f"Make your wedding card fully in {lang.name} ({lang.native}): the heading, the invitation line, names, dates and the "
            f"invite page your guests open, with fonts that write every {lang.name} letter correctly.",
            WEDDING_EN, WEDDING_HI if code in ("hi", "mr") else []))
    for style, (base, h1, name, local) in STYLE_PAGES.items():
        found.append(Landing(
            f"{base}-{SUFFIX}", h1, name, local, "wedding", f"/create?style={style}", "/demo/en", f"/samples/{style}.jpg",
            f"The {STYLES[style].name} design: {STYLES[style].description} Make the {name} card and a matching card for every "
            f"function, then share it on WhatsApp as a card, a PDF or a live invite page.",
            WEDDING_EN, WEDDING_HI))
    for key, t in events.TYPES.items():
        base = TYPE_SLUGS.get(key) or t.name.lower().replace("'", "").replace(" ", "-")
        cat = events.CATEGORIES[t.category]
        en, hi = _wording(t)
        found.append(Landing(
            f"{base}-{SUFFIX}", f"{t.name} Invitation Card", t.name, t.headline_hi, t.category,
            f"/create?event={key}", f"/demo/event/{key}", f"/samples/event/{key}.jpg",
            f"Make a {t.name} invitation in 60 seconds: pick a design, type the details and it's ready to download and share. "
            f"{cat.blurb}",
            en, hi))
    by_slug = {p.slug: p for p in found}
    assert len(by_slug) == len(found), "two landing pages share a URL"
    return by_slug


def related(page: Landing, limit: int = 8) -> list[Landing]:
    same = [p for p in pages().values() if p.category == page.category and p.slug != page.slug]
    other = [p for p in pages().values() if p.category != page.category]
    return (same + other)[:limit]


FOOTER_SLUGS = [f"wedding-{SUFFIX}", f"hindi-wedding-{SUFFIX}", f"kids-birthday-{SUFFIX}", f"griha-pravesh-{SUFFIX}",
                f"satyanarayan-puja-{SUFFIX}", f"wedding-anniversary-{SUFFIX}", f"baby-shower-godh-bharai-{SUFFIX}",
                f"inauguration-opening-ceremony-{SUFFIX}", f"nikah-{SUFFIX}"]


def footer_links() -> list[Landing]:
    return [pages()[s] for s in FOOTER_SLUGS if s in pages()]


def for_create_url(url: str) -> Landing | None:
    """The landing page that opens the creator at this URL, e.g. '/create?event=griha_pravesh'."""
    return next((p for p in pages().values() if p.create_url == url), None)
