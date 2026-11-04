"""Price list (A3), functions, languages and the style library (C4).

Edit prices and wording here; everything on the website, order form and
payments reads from this file.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Package:
    key: str
    name: str
    price: int  # INR
    tagline: str
    features: tuple[str, ...]
    function_cards: bool = False
    video: bool = False
    rsvp: bool = False
    express: bool = False
    popular: bool = False
    event_page: bool = False  # cinematic invite page + RSVP via the general link
    listed: bool = True  # shown in the pricing grid / order form


@dataclass(frozen=True)
class Resolution:
    key: str
    name: str
    width: int
    height: int
    price: int  # INR; 0 = free
    use: str


# Instant invitations: download size tiers. Edit prices here.
RESOLUTIONS: dict[str, Resolution] = {
    r.key: r
    for r in [
        Resolution("free", "Standard", 720, 900, 0, "Quick sharing, with a small credit"),
        Resolution("1080", "Full HD", 1080, 1350, 9, "Perfect for WhatsApp & Instagram"),
        Resolution("2k", "2K", 2048, 2560, 49, "Extra crisp + 🎬 video invite with music"),
        Resolution("4k", "4K", 3840, 4800, 99, "Print-ready + 🎬 video invite with music"),
    ]
}


@dataclass(frozen=True)
class Addon:
    key: str
    name: str
    price: int  # INR
    description: str
    selectable: bool = True  # False = only bought later (e.g. extra revision)


PACKAGES: dict[str, Package] = {
    p.key: p
    for p in [
        Package(
            "instant",
            "Instant",
            9,
            "Create it yourself in 60 seconds",
            (
                "Free Standard download, HD from ₹9",
                "A card for the wedding and every function, no watermark",
                "Cinematic invite page to share on WhatsApp, with RSVP",
                "A personal invite for each guest by WhatsApp or SMS, with their name",
                "Your language, your style",
                "Sent to your email",
            ),
            function_cards=True,
            event_page=True,
            listed=False,
        ),
        Package(
            "basic",
            "Basic",
            499,
            "One stunning invitation card",
            (
                "1 HD invitation card (1080 × 1350, WhatsApp & Instagram ready)",
                "Your choice of style and language",
                "Couple photo blended into the design (optional)",
                "2 free revisions",
                "Delivered on WhatsApp & email within 48 hours",
            ),
        ),
        Package(
            "video",
            "Video",
            1499,
            "Invitation card + animated video",
            (
                "Everything in Basic",
                "30-second animated video invite with shehnai music",
                "Perfect for WhatsApp status and Instagram reels",
                "2 free revisions",
            ),
            video=True,
            popular=True,
        ),
        Package(
            "premium",
            "Premium",
            2999,
            "The complete digital shaadi experience",
            (
                "Cinematic invite page: palace doors open, petals fall, music plays",
                "Personal WhatsApp invite for every guest, with their name & only their functions",
                "Live family console: who opened, who's coming, headcount per function, food & pickups",
                "A matching card for every function (Haldi, Mehndi, Sangeet…)",
                "Animated video invite + shagun via UPI + add-to-calendar",
                "Priority 24-hour delivery · 2 free revisions",
            ),
            function_cards=True,
            video=True,
            rsvp=True,
            express=True,
        ),
    ]
}

ADDONS: dict[str, Addon] = {
    a.key: a
    for a in [
        Addon("function_cards", "Card for every function", 599, "A separate matching card for each function you add."),
        Addon("rsvp", "Smart Guest Invites", 999, "Cinematic invite page + personal WhatsApp link for every guest + live RSVP & headcount console."),
        Addon("express", "Express 24-hour delivery", 299, "Jump the queue — proof within 24 hours."),
        Addon("extra_revision", "Extra revision", 199, "One more round of changes after your free ones.", False),
    ]
}

# Wedding functions, in the order they usually happen.
FUNCTIONS: dict[str, str] = {
    "engagement": "Engagement / Roka",
    "tilak": "Tilak",
    "haldi": "Haldi",
    "mehndi": "Mehndi",
    "sangeet": "Sangeet",
    "wedding": "Wedding Ceremony",
    "nikah": "Nikah",
    "reception": "Reception",
}

@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native: str
    headline: str
    invite_line: str | None  # None = use the English line
    connector: str = "&"


LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in [
        Language("en", "English", "English", "Wedding Invitation", None),
        Language("hi", "Hindi", "हिन्दी", "शुभ विवाह", "आप सपरिवार सादर आमंत्रित हैं", "संग"),
        Language("mr", "Marathi", "मराठी", "शुभ विवाह", "सस्नेह निमंत्रण"),
        Language("bn", "Bengali", "বাংলা", "শুভ বিবাহ", "সাদর আমন্ত্রণ"),
        Language("gu", "Gujarati", "ગુજરાતી", "શુભ લગ્ન", None),
        Language("pa", "Punjabi", "ਪੰਜਾਬੀ", "ਸ਼ੁਭ ਵਿਆਹ", None),
        Language("ta", "Tamil", "தமிழ்", "திருமண அழைப்பிதழ்", None),
        Language("te", "Telugu", "తెలుగు", "వివాహ ఆహ్వానం", None),
        Language("kn", "Kannada", "ಕನ್ನಡ", "ಶುಭ ವಿವಾಹ", None),
        Language("ml", "Malayalam", "മലയാളം", "വിവാഹ ക്ഷണം", None),
    ]
}

ENGLISH_INVITE_LINE = "Together with their families, request the pleasure of your company at the wedding of"


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    description: str
    prompt: str  # what the background should look like (no text — we add text ourselves)
    motif: str  # drawing used by the offline generator
    bg_top: tuple[int, int, int]
    bg_bottom: tuple[int, int, int]
    accent: tuple[int, int, int]
    text_primary: tuple[int, int, int]
    text_secondary: tuple[int, int, int]
    panel: tuple[int, int, int, int]  # translucent panel behind the text
    suits: tuple[str, ...] = field(default_factory=tuple)
    occasions: tuple[str, ...] = ("wedding",)  # wedding pickers only list styles made for weddings


STYLES: dict[str, Style] = {
    s.key: s
    for s in [
        Style(
            "north_indian",
            "Royal North Indian",
            "Maroon and gold, marigold torans, a palace jharokha and glowing diyas.",
            "a royal North Indian Hindu wedding invitation background in deep maroon and antique gold, "
            "an ornate Rajasthani jharokha arch framing the page, hanging marigold and mango-leaf torans, "
            "a row of glowing brass diyas along the bottom, fine gold paisley borders, subtle silk texture",
            "arch",
            (110, 18, 36), (58, 8, 20), (214, 172, 82), (246, 214, 138), (250, 236, 210), (40, 6, 14, 120),
            ("wedding", "tilak", "engagement", "reception"),
        ),
        Style(
            "south_indian",
            "Temple South Indian",
            "Temple gopuram, banana leaves, jasmine and brass kuthuvilakku lamps.",
            "a traditional South Indian temple wedding invitation background, a golden temple gopuram silhouette "
            "at the top, banana leaves and jasmine strings on the sides, brass kuthuvilakku lamps, kolam patterns, "
            "rich emerald green with temple red and gold accents, kanjeevaram silk border texture",
            "temple",
            (16, 74, 52), (8, 40, 28), (222, 178, 76), (248, 220, 140), (240, 246, 232), (4, 28, 18, 120),
            ("wedding", "reception"),
        ),
        Style(
            "bengali",
            "Bengali Alpana",
            "Red and white alpana art, conch shells and a shola topor motif.",
            "a Bengali wedding invitation background with traditional white alpana (rangoli) art on red, "
            "conch shells (shankha), a decorative shola topor motif, a red-and-white saree border, "
            "fish and lotus folk motifs, warm gold highlights",
            "alpana",
            (176, 28, 30), (120, 12, 18), (255, 236, 200), (255, 246, 226), (255, 236, 214), (70, 6, 10, 110),
            ("wedding", "reception"),
        ),
        Style(
            "muslim_nikah",
            "Elegant Nikah",
            "Emerald and ivory with Mughal arches, lanterns and geometric patterns.",
            "an elegant Muslim nikah invitation background, emerald green and ivory with gold, a Mughal arch, "
            "hanging lanterns, a crescent moon, intricate Islamic geometric patterns along the border, "
            "soft floral vines, no human figures",
            "crescent",
            (14, 70, 62), (6, 36, 34), (220, 190, 120), (246, 226, 168), (236, 246, 240), (2, 26, 24, 120),
            ("nikah", "reception"),
        ),
        Style(
            "christian",
            "Classic Christian",
            "Ivory and sage, white roses, doves and a church arch.",
            "a classic Christian wedding invitation background, ivory and soft sage green, watercolor white roses "
            "and eucalyptus, a pair of white doves, a delicate gothic church window arch, gold foil accents, airy and light",
            "floral",
            (250, 246, 236), (232, 238, 226), (176, 146, 86), (98, 78, 44), (84, 92, 76), (255, 255, 255, 150),
            ("wedding", "reception", "engagement"),
        ),
        Style(
            "haldi",
            "Haldi Sunshine",
            "Bright turmeric yellow, marigolds and mango leaves.",
            "a cheerful Haldi ceremony invitation background, bright turmeric yellow and marigold orange, "
            "marigold flower garlands, mango leaves, a brass urli bowl with turmeric paste, playful splashes of haldi",
            "marigold",
            (252, 196, 40), (236, 142, 18), (140, 66, 8), (110, 40, 6), (96, 46, 6), (255, 244, 200, 130),
            ("haldi",),
        ),
        Style(
            "mehndi",
            "Mehndi Garden",
            "Henna green and magenta with paisley mehndi patterns.",
            "a vibrant Mehndi ceremony invitation background, henna green with magenta and marigold accents, "
            "intricate mehndi paisley line patterns, hanging colourful tassels and umbrellas, festive garden feel",
            "paisley",
            (54, 98, 40), (30, 62, 24), (240, 176, 64), (255, 226, 140), (246, 240, 220), (16, 36, 10, 120),
            ("mehndi", "sangeet"),
        ),
        Style(
            "modern_minimal",
            "Modern Pastel",
            "Blush pink and gold foil with soft watercolor florals.",
            "a modern minimal Indian wedding invitation background, blush pink and cream, soft pastel watercolor "
            "peonies and marigolds in the corners, thin gold foil line-art arch, lots of clean space",
            "floral",
            (252, 236, 232), (244, 218, 214), (196, 150, 90), (122, 60, 70), (110, 80, 80), (255, 255, 255, 140),
            ("wedding", "engagement", "sangeet", "reception"),
        ),
        Style(
            "kids_party", "Balloon Party", "Bright balloons, confetti and bunting for kids' parties.",
            "a joyful kids' birthday party invitation background with colourful balloons, confetti, bunting flags and "
            "a cute cake, bright happy pastel colours, playful and fun",
            "balloons", (255, 240, 200), (255, 196, 210), (214, 51, 132), (92, 30, 110), (80, 50, 90), (255, 255, 255, 165),
            occasions=("event",),
        ),
        Style(
            "golden_celebration", "Golden Gala", "Deep navy with gold confetti and sparkles.",
            "an elegant celebration invitation background, deep navy blue and gold, gold confetti, sparkles and "
            "bokeh lights, champagne glow, luxurious and festive",
            "stars", (22, 32, 72), (8, 12, 32), (226, 186, 92), (246, 214, 138), (240, 236, 226), (4, 8, 24, 120),
            occasions=("event",),
        ),
        Style(
            "divine_puja", "Divine Puja", "Saffron and gold with diyas, marigolds and temple bells.",
            "a sacred Hindu puja invitation background, saffron and maroon with gold, brass diyas, marigold garlands, "
            "kalash with mango leaves, temple bells, om motif, soft divine glow",
            "arch", (214, 96, 24), (128, 30, 14), (255, 214, 102), (255, 236, 170), (255, 244, 224), (80, 16, 4, 120),
            occasions=("event",),
        ),
        Style(
            "festive_lights", "Festive Lights", "Purple night sky, string lights and glowing diyas.",
            "a festive celebration invitation background with glowing string lights, diyas, lanterns and fireworks, "
            "deep purple night sky with gold sparkle",
            "stars", (70, 28, 96), (22, 8, 44), (255, 200, 80), (255, 222, 140), (245, 236, 255), (16, 4, 32, 120),
            occasions=("event",),
        ),
        Style(
            "corporate_classic", "Corporate Classic", "Clean white with navy and gold lines.",
            "a clean modern corporate event invitation background, white with navy blue and gold geometric lines and a "
            "subtle ribbon, premium and minimal, plenty of empty space",
            "lines", (250, 251, 253), (226, 232, 242), (30, 64, 124), (20, 40, 90), (55, 65, 85), (255, 255, 255, 175),
            occasions=("event",),
        ),
    ]
}


def card_style_for(order_style: str, function_key: str) -> str:
    """Haldi and mehndi cards look best in their own festive style; everything else keeps the main style."""
    if function_key in ("haldi", "mehndi") and order_style not in ("christian", "modern_minimal"):
        return function_key
    return order_style
