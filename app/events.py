"""Occasions beyond weddings: categories, event types and their wording.

Weddings keep their own flow (event_type "wedding"). Every other event type reuses the same
order, card, invite-page, RSVP and e-invite engine, with the fields and wording defined here.
Order fields are reused: bride_name = main name, groom_name = second name (optional),
occasion_detail = the type's extra detail (age, years, theme, product…), wedding_date = event date.

Event-specific wording is provided in English and Hindi; other languages fall back to English
for these lines while the rest of the invite page stays in the chosen language.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EventType:
    key: str
    name: str
    category: str
    icon: str
    headline: str
    headline_hi: str
    primary_label: str
    styles: tuple[str, ...]
    secondary_label: str = ""  # empty = no second name field
    secondary_required: bool = False
    detail_label: str = ""
    detail_hint: str = ""
    detail_fmt: str = "{detail}"  # how the detail line reads on the card / invite
    detail_fmt_hi: str = "{detail}"
    kicker: str = "You're invited to"
    kicker_hi: str = "आप सादर आमंत्रित हैं"
    invocation: str = ""  # ganesh | bismillah | "" (none)
    name_role: str = "names"  # names = script font; brand = Cinzel (company names)
    demo: tuple[str, str, str] = ("Aarav", "", "")  # primary, secondary, detail for sample cards
    photo_labels: tuple[str, str] = ("Photo of the guest of honour", "Second photo")


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    name_hi: str
    icon: str
    blurb: str
    types: tuple[str, ...]


PUJA_STYLES = ("divine_puja", "haldi", "north_indian", "festive_lights")
BABY_STYLES = ("modern_minimal", "kids_party", "haldi", "divine_puja")

_TYPES = [
    # Birthdays
    EventType("kids_birthday", "Kids' Birthday", "birthday", "🎈", "Birthday Party", "जन्मदिन समारोह", "Child's name",
              ("kids_party", "golden_celebration", "modern_minimal"), detail_label="Turning (age)", detail_hint="5",
              detail_fmt="turns {detail}!", detail_fmt_hi="का {detail}वाँ जन्मदिन", kicker="Join us to celebrate",
              kicker_hi="आइए, साथ मनाएँ", demo=("Aarav", "", "5"), photo_labels=("Birthday star's photo", "")),
    EventType("milestone_birthday", "Milestone Birthday", "birthday", "🎂", "Milestone Birthday", "विशेष जन्मदिन", "Name",
              ("golden_celebration", "modern_minimal", "north_indian"), detail_label="Milestone age", detail_hint="60",
              detail_fmt="celebrating {detail} wonderful years", detail_fmt_hi="का {detail}वाँ जन्मदिन",
              kicker="Join us to celebrate", kicker_hi="आइए, साथ मनाएँ", demo=("Ramesh Sharma", "", "60"),
              photo_labels=("Birthday person's photo", "")),
    EventType("theme_party", "Theme Party", "birthday", "🥳", "Theme Party", "थीम पार्टी", "Hosted by / birthday person",
              ("kids_party", "golden_celebration", "festive_lights"), detail_label="Theme", detail_hint="Bollywood Night",
              detail_fmt="Theme: {detail}", detail_fmt_hi="थीम: {detail}", kicker="Get ready for a", kicker_hi="आइए, मस्ती करें",
              demo=("Riya", "", "Bollywood Night"), photo_labels=("Host's photo", "")),
    # Anniversaries
    EventType("wedding_anniversary", "Wedding Anniversary", "anniversary", "💞", "Wedding Anniversary", "विवाह वर्षगाँठ",
              "Partner's name", ("golden_celebration", "modern_minimal", "north_indian"), secondary_label="Partner's name",
              secondary_required=True, detail_label="Years together", detail_hint="10",
              detail_fmt="celebrating {detail} years of togetherness", detail_fmt_hi="विवाह की {detail}वीं वर्षगाँठ",
              kicker="Join us to celebrate", kicker_hi="आइए, साथ मनाएँ", demo=("Neha", "Rahul", "10"),
              photo_labels=("Partner's photo", "Partner's photo")),
    EventType("milestone_anniversary", "Silver / Golden Jubilee", "anniversary", "💍", "Anniversary Celebration",
              "वर्षगाँठ समारोह", "Partner's name", ("golden_celebration", "modern_minimal", "north_indian"),
              secondary_label="Partner's name", secondary_required=True, detail_label="Years (25 = Silver, 50 = Golden)",
              detail_hint="25", detail_fmt="{detail} glorious years together", detail_fmt_hi="साथ के {detail} सुनहरे वर्ष",
              kicker="Join us to celebrate", kicker_hi="आइए, साथ मनाएँ", demo=("Sunita", "Vijay", "25"),
              photo_labels=("Partner's photo", "Partner's photo")),
    # Religious pujas
    EventType("satyanarayan_puja", "Satyanarayan Puja", "puja", "🪔", "Shri Satyanarayan Puja", "श्री सत्यनारायण पूजा",
              "Host family", PUJA_STYLES, detail_label="Followed by (optional)", detail_hint="Aarti & Prasad",
              detail_fmt="followed by {detail}", detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to",
              invocation="ganesh", demo=("The Sharma Family", "", "Aarti & Prasad"), photo_labels=("Family photo", "")),
    EventType("rudrabhishek", "Rudrabhishek", "puja", "🔱", "Rudrabhishek", "रुद्राभिषेक", "Host family", PUJA_STYLES,
              detail_label="Followed by (optional)", detail_hint="Bhandara", detail_fmt="followed by {detail}",
              detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to", invocation="ganesh",
              demo=("The Mishra Family", "", "Bhandara"), photo_labels=("Family photo", "")),
    EventType("ganesh_chaturthi", "Ganesh Chaturthi", "puja", "🐘", "Ganesh Chaturthi Utsav", "गणेश चतुर्थी उत्सव",
              "Host family", PUJA_STYLES, detail_label="Followed by (optional)", detail_hint="Aarti & Mahaprasad",
              detail_fmt="followed by {detail}", detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to",
              invocation="ganesh", demo=("The Patil Family", "", "Aarti & Mahaprasad"), photo_labels=("Family photo", "")),
    EventType("griha_pravesh", "Griha Pravesh", "puja", "🏡", "Griha Pravesh", "गृह प्रवेश", "Host family", PUJA_STYLES,
              detail_label="Followed by (optional)", detail_hint="Lunch", detail_fmt="followed by {detail}",
              detail_fmt_hi="तत्पश्चात {detail}", kicker="Please bless our new home at our", kicker_hi="हमारे नए घर के",
              invocation="ganesh", demo=("The Gupta Family", "", "Lunch"), photo_labels=("Family photo", "")),
    EventType("krishna_janmashtami", "Krishna Janmashtami", "puja", "🦚", "Shri Krishna Janmashtami", "श्री कृष्ण जन्माष्टमी",
              "Host family", PUJA_STYLES, detail_label="Followed by (optional)", detail_hint="Midnight Aarti & Prasad",
              detail_fmt="followed by {detail}", detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to",
              invocation="ganesh", demo=("The Yadav Family", "", "Midnight Aarti & Prasad"), photo_labels=("Family photo", "")),
    EventType("durga_puja", "Durga Puja / Navratri", "puja", "🔱", "Navratri & Durga Puja", "नवरात्रि एवं दुर्गा पूजा",
              "Host family / committee", ("bengali", "divine_puja", "mehndi", "festive_lights"), detail_label="Followed by (optional)",
              detail_hint="Garba Night", detail_fmt="followed by {detail}", detail_fmt_hi="तत्पश्चात {detail}",
              kicker="You are cordially invited to", invocation="ganesh", demo=("The Bose Family", "", "Garba Night"),
              photo_labels=("Family photo", "")),
    EventType("diwali_puja", "Diwali / Laxmi Puja", "puja", "🪔", "Diwali Laxmi Puja", "दीपावली लक्ष्मी पूजन", "Host family",
              ("festive_lights", "divine_puja", "north_indian"), detail_label="Followed by (optional)", detail_hint="Dinner & Fireworks",
              detail_fmt="followed by {detail}", detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to",
              invocation="ganesh", demo=("The Agarwal Family", "", "Dinner & Fireworks"), photo_labels=("Family photo", "")),
    # Chhath honours Surya Dev and Chhathi Maiya: the card opens with "Jai Chhathi Maiya", not a Ganesh invocation
    EventType("chhath_puja", "Chhath Puja", "puja", "🌅", "Chhath Mahaparv", "छठ महापर्व", "Host family",
              ("divine_puja", "haldi", "festive_lights", "north_indian"), detail_label="Rituals (optional)",
              detail_hint="Sandhya Arghya & Usha Arghya", detail_fmt="{detail}", detail_fmt_hi="{detail}",
              kicker="Jai Chhathi Maiya! Join us for the", kicker_hi="जय छठी मइया! आप सपरिवार आमंत्रित हैं",
              demo=("The Singh Family", "", "Sandhya Arghya & Usha Arghya"), photo_labels=("Family photo", "")),
    EventType("sundar_kand", "Sundar Kand Path", "puja", "🙏", "Shri Sundar Kand Path", "श्री सुंदरकांड पाठ", "Host family",
              PUJA_STYLES, detail_label="Followed by (optional)", detail_hint="Prasad", detail_fmt="followed by {detail}",
              detail_fmt_hi="तत्पश्चात {detail}", kicker="You are cordially invited to", invocation="ganesh",
              demo=("The Tiwari Family", "", "Prasad"), photo_labels=("Family photo", "")),
    # Baby & family ceremonies
    EventType("baby_shower", "Baby Shower (Godh Bharai / Seemandham)", "baby", "🤰", "Godh Bharai", "गोद भराई",
              "Mother-to-be", BABY_STYLES, secondary_label="Father-to-be (optional)", kicker="Join us to bless",
              kicker_hi="आशीर्वाद देने पधारें", invocation="ganesh", demo=("Priya", "Rohan", ""),
              photo_labels=("Mother-to-be's photo", "Father-to-be's photo")),
    EventType("namakaran", "Namakaran (Naming Ceremony)", "baby", "👶", "Namkaran Sanskar", "नामकरण संस्कार",
              "Baby's name (or 'Baby of Priya & Rohan')", BABY_STYLES, kicker="Join us for the", invocation="ganesh",
              demo=("Baby Myra", "", ""), photo_labels=("Baby's photo", "")),
    EventType("annaprashan", "Annaprashan (First Rice)", "baby", "🍚", "Annaprashan Sanskar", "अन्नप्राशन संस्कार",
              "Baby's name", BABY_STYLES, kicker="Join us for the", invocation="ganesh", demo=("Vihaan", "", ""),
              photo_labels=("Baby's photo", "")),
    EventType("mundan", "Mundan Ceremony", "baby", "✂️", "Mundan Sanskar", "मुंडन संस्कार", "Child's name", BABY_STYLES,
              kicker="Join us for the", invocation="ganesh", demo=("Kabir", "", ""), photo_labels=("Child's photo", "")),
    EventType("upanayanam", "Upanayanam (Janeu)", "baby", "🧵", "Upanayan Sanskar", "उपनयन संस्कार (जनेऊ)", "Name",
              ("divine_puja", "haldi", "south_indian"), kicker="You are cordially invited to", invocation="ganesh",
              demo=("Aditya", "", ""), photo_labels=("Photo", "")),
    # Festivals & parties
    EventType("lohri_sankranti", "Lohri / Sankranti", "festival", "🔥", "Lohri & Makar Sankranti", "लोहड़ी एवं मकर संक्रांति",
              "Hosted by", ("haldi", "festive_lights", "golden_celebration"), kicker="Celebrate with us", kicker_hi="आइए, साथ मनाएँ",
              demo=("The Gill Family", "", ""), photo_labels=("Host family photo", "")),
    EventType("eid_dawat", "Eid Dawat", "festival", "🌙", "Eid Mubarak · Dawat", "ईद मुबारक · दावत", "Hosted by",
              ("muslim_nikah", "golden_celebration", "festive_lights"), kicker="Join us for a festive", kicker_hi="आइए, साथ मनाएँ",
              invocation="bismillah", demo=("The Khan Family", "", ""), photo_labels=("Host family photo", "")),
    EventType("christmas_newyear", "Christmas / New Year", "festival", "🎄", "Christmas & New Year Party", "क्रिसमस और नववर्ष पार्टी",
              "Hosted by", ("festive_lights", "christian", "golden_celebration"), kicker="Join us for a", kicker_hi="आइए, साथ मनाएँ",
              demo=("The D'Souza Family", "", ""), photo_labels=("Host family photo", "")),
    EventType("kitty_party", "Kitty Party", "festival", "👛", "Kitty Party", "किटी पार्टी", "Hosted by",
              ("golden_celebration", "modern_minimal", "kids_party"), detail_label="Theme (optional)", detail_hint="Retro Glam",
              detail_fmt="Theme: {detail}", detail_fmt_hi="थीम: {detail}", kicker="You're invited to a", kicker_hi="आइए, मस्ती करें",
              demo=("Meera", "", "Retro Glam"), photo_labels=("Host's photo", "")),
    EventType("family_reunion", "Family Reunion", "festival", "👨‍👩‍👧‍👦", "Family Reunion", "पारिवारिक मिलन", "Family name",
              ("golden_celebration", "modern_minimal", "north_indian"), kicker="Let's come together for our",
              kicker_hi="आइए, फिर साथ आएँ", demo=("The Verma Family", "", ""), photo_labels=("Family photo", "")),
    # Corporate & business
    EventType("grand_opening", "Grand Opening / Inauguration", "corporate", "🎀", "Grand Opening", "भव्य उद्घाटन",
              "Business / store name", ("corporate_classic", "golden_celebration", "divine_puja"), detail_label="Inaugurated by (optional)",
              detail_hint="Shri R. K. Sharma", detail_fmt="inaugurated by {detail}", detail_fmt_hi="उद्घाटनकर्ता: {detail}",
              kicker="You are cordially invited to the", name_role="brand", demo=("Shree Jewellers", "", "Shri R. K. Sharma"),
              photo_labels=("Logo or storefront photo", "")),
    EventType("annual_day", "Office Annual Day", "corporate", "🏆", "Annual Day Celebration", "वार्षिक दिवस समारोह",
              "Company name", ("corporate_classic", "golden_celebration", "festive_lights"), detail_label="Theme (optional)",
              detail_hint="Rise Together", detail_fmt="Theme: {detail}", detail_fmt_hi="थीम: {detail}",
              kicker="You are cordially invited to the", name_role="brand", demo=("Nexus Technologies", "", "Rise Together"),
              photo_labels=("Company logo", "")),
    EventType("product_launch", "Product Launch", "corporate", "🚀", "Product Launch", "उत्पाद लॉन्च", "Company name",
              ("corporate_classic", "golden_celebration", "festive_lights"), detail_label="Product name", detail_hint="Aurora X1",
              detail_fmt="introducing {detail}", detail_fmt_hi="प्रस्तुत है {detail}", kicker="You are invited to the",
              name_role="brand", demo=("Nexus Technologies", "", "Aurora X1"), photo_labels=("Product or logo image", "")),
]
TYPES: dict[str, EventType] = {t.key: t for t in _TYPES}

CATEGORIES: dict[str, Category] = {
    c.key: c
    for c in [
        Category("wedding", "Weddings", "विवाह", "💍", "Shaadi, Nikah, church weddings and every function.", ()),
        Category("birthday", "Birthdays", "जन्मदिन", "🎂", "Kids' parties, milestone birthdays and theme nights.",
                 ("kids_birthday", "milestone_birthday", "theme_party")),
        Category("anniversary", "Anniversaries", "वर्षगाँठ", "💞", "Wedding anniversaries and Silver/Golden jubilees.",
                 ("wedding_anniversary", "milestone_anniversary")),
        Category("puja", "Religious Pujas", "धार्मिक पूजा", "🪔", "Satyanarayan, Griha Pravesh, Diwali, Chhath, Navratri and more.",
                 ("satyanarayan_puja", "rudrabhishek", "ganesh_chaturthi", "griha_pravesh", "krishna_janmashtami",
                  "durga_puja", "diwali_puja", "chhath_puja", "sundar_kand")),
        Category("baby", "Baby & Family Ceremonies", "शिशु एवं पारिवारिक संस्कार", "👶",
                 "Godh Bharai, Namakaran, Annaprashan, Mundan, Janeu.",
                 ("baby_shower", "namakaran", "annaprashan", "mundan", "upanayanam")),
        Category("festival", "Festivals & Parties", "त्योहार एवं पार्टियाँ", "🎉", "Lohri, Eid, Christmas, kitty parties, reunions.",
                 ("lohri_sankranti", "eid_dawat", "christmas_newyear", "kitty_party", "family_reunion")),
        Category("corporate", "Corporate & Business", "कॉर्पोरेट एवं व्यवसाय", "🏢", "Inaugurations, annual days and launches.",
                 ("grand_opening", "annual_day", "product_launch")),
    ]
}

INVITE_PARA = {
    "birthday": ("Please join us to celebrate {names}'s birthday with fun, food and lots of love. Your presence will make the day extra special.",
                 "{names} के जन्मदिन के इस खास मौके पर आप सादर आमंत्रित हैं। आपकी उपस्थिति हमारी खुशी को दोगुना कर देगी।"),
    "anniversary": ("{hosts} invite you to celebrate {names} and their beautiful journey of love. Your presence and blessings will make the day golden.",
                    "{names} की वर्षगाँठ के शुभ अवसर पर आप सपरिवार सादर आमंत्रित हैं। आपकी उपस्थिति हमारे लिए आशीर्वाद होगी।"),
    "puja": ("With the blessings of the Almighty, {hosts} cordially invite you and your family to the {headline}. Kindly grace the occasion and receive the divine blessings and prasad.",
             "प्रभु की असीम कृपा से {hosts} द्वारा आयोजित {headline} में आप सपरिवार सादर आमंत्रित हैं। कृपया पधारकर प्रसाद ग्रहण करें।"),
    "baby": ("{hosts} joyfully invite you to the {headline} of {names}. Please join us and shower your blessings on our little one.",
             "{names} के {headline} के पावन अवसर पर आप सपरिवार सादर आमंत्रित हैं। कृपया पधारकर आशीर्वाद दें।"),
    "festival": ("{hosts} invite you and your family to celebrate {headline} with us. Good food, music and great company await!",
                 "{headline} के शुभ अवसर पर {hosts} की ओर से आप सपरिवार सादर आमंत्रित हैं।"),
    "corporate": ("{hosts} cordially invite you to the {headline} of {names}. We look forward to welcoming you.",
                  "{names} के {headline} में आप सादर आमंत्रित हैं। आपकी उपस्थिति हमारे लिए सम्मान की बात होगी।"),
}
SCHEDULE_TITLE = ("Event Details", "कार्यक्रम")
DEFAULT_HOSTS = ("Our family", "हमारा परिवार")


MAX_SESSIONS = 4
# Suggestions for "+ Add more days or sessions": the parts families usually list on a multi-day card.
SESSION_IDEAS: dict[str, tuple[str, ...]] = {
    "chhath_puja": ("Nahay Khay", "Kharna", "Sandhya Arghya", "Usha Arghya"),
    "durga_puja": ("Ghatasthapana", "Ashtami Puja", "Kanya Pujan", "Garba Night", "Dussehra"),
    "ganesh_chaturthi": ("Sthapana", "Maha Aarti", "Bhandara", "Visarjan"),
    "diwali_puja": ("Dhanteras", "Laxmi Puja", "Govardhan Puja", "Bhai Dooj"),
    "krishna_janmashtami": ("Jhanki Darshan", "Midnight Aarti", "Dahi Handi"),
    "griha_pravesh": ("Vastu Puja", "Havan", "Bhoj"),
    "upanayanam": ("Haldi", "Janeu Sanskar", "Bhoj"),
    "mundan": ("Puja", "Mundan", "Bhoj"),
    "lohri_sankranti": ("Lohri Bonfire", "Makar Sankranti Lunch"),
    "eid_dawat": ("Chand Raat", "Eid Dawat"),
    "grand_opening": ("Puja", "Ribbon Cutting", "Lunch"),
    "annual_day": ("Awards", "Cultural Evening", "Dinner"),
    "puja": ("Katha", "Aarti", "Havan", "Bhandara"),
    "baby": ("Puja", "Ceremony", "Lunch"),
    "birthday": ("Cake Cutting", "Dinner", "After Party"),
    "anniversary": ("Puja", "Dinner", "Dance Night"),
    "festival": ("Puja", "Dinner", "Party"),
    "corporate": ("Registration", "Keynote", "Dinner"),
}


def session_ideas(key: str) -> tuple[str, ...]:
    t = TYPES.get(key)
    return SESSION_IDEAS.get(key) or (SESSION_IDEAS.get(t.category, ()) if t else ())


def jubilee(detail: str) -> tuple[str, str] | None:
    try:
        years = int(str(detail).strip())
    except ValueError:
        return None
    return {25: ("Silver Jubilee", "रजत जयंती"), 50: ("Golden Jubilee", "स्वर्ण जयंती"),
            60: ("Diamond Jubilee", "हीरक जयंती"), 75: ("Platinum Jubilee", "प्लेटिनम जयंती")}.get(years)


def texts(order) -> dict:
    """Everything the card, invite page and e-invite need to word a non-wedding event."""
    t = TYPES[order.event_type]
    hi = order.language == "hi"
    local = order.language != "en"
    primary = (order.bride_name_local if local and order.bride_name_local else order.bride_name).strip()
    secondary = (order.groom_name_local if local and order.groom_name_local else order.groom_name).strip()
    names = f"{primary} & {secondary}" if secondary else primary
    headline = t.headline_hi if hi else t.headline
    if t.key == "milestone_anniversary" and (j := jubilee(order.occasion_detail)):
        headline = j[1] if hi else j[0]
    detail = ""
    if order.occasion_detail.strip() and t.detail_label:
        detail = (t.detail_fmt_hi if hi else t.detail_fmt).format(detail=order.occasion_detail.strip())
    hosts = (order.event.hosts if order.event and order.event.hosts else "") or (
        primary if t.category in ("puja", "festival", "corporate") else DEFAULT_HOSTS[hi])
    para = INVITE_PARA[t.category][hi].format(hosts=hosts, names=names, headline=headline)
    gifts = {
        "wishes_label": ("Your wishes 💌", "आपकी शुभकामनाएँ 💌"), "gift_title": ("Send a gift 🎁", "उपहार भेजें 🎁"),
        "gift_text": ("Can't make it in person? Send your gift via UPI.", "आ नहीं पा रहे? UPI से उपहार भेजें।"),
        "gift_btn": ("Send gift via UPI", "UPI से उपहार भेजें"),
    }
    return {
        **{k: v[hi] for k, v in gifts.items()},
        "type": t, "headline": headline, "kicker": t.kicker_hi if hi else t.kicker, "primary": primary,
        "secondary": secondary, "names": names, "detail": detail, "hosts": hosts, "para": para,
        "schedule_title": SCHEDULE_TITLE[hi], "initials": (primary[:1] + (("&" + secondary[:1]) if secondary else "")),
    }
