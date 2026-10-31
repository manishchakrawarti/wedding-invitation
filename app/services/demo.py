"""Ready-made sample weddings, one per language, for the website's live demos and for Instagram."""
import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.config import APP_DIR
from app.db import SessionLocal
from app.models import EventDetails, Invitee, Order, OrderStatus, utcnow
from app.services import invites, orders, pipeline
from app.utils import new_token

log = logging.getLogger(__name__)

HINDU = ["haldi", "mehndi", "sangeet", "wedding", "reception"]
SOUTH = ["engagement", "haldi", "wedding", "reception"]

# Each demo is culturally matched: names, city, venues, families and the functions that wedding would have.
DEMOS: dict[str, dict] = {
    "en": dict(
        style="north_indian", bride=("Ananya", ""), groom=("Arjun", ""), city="Jaipur",
        venue="The Royal Palace Gardens", address="Amer Road", home="Sharma Haveli", reception="Rambagh Palace",
        hosts="The Sharma & Mehta families", blessing_line="With the blessings of Late Smt. Kamla Devi Sharma",
        families=("Mrs & Mr Rakesh Sharma", "Mrs & Mr Vikram Mehta"), guest="Sharma Family", functions=HINDU,
        hashtag="#AnanyaKaArjun", wish="Bahut bahut badhaai! Can't wait to dance at the sangeet 💃",
        story="We met in a Jaipur bookshop, both reaching for the last copy of the same novel.\n"
              "Arjun let Ananya have it — on the condition that she'd tell him the ending over chai.\n"
              "Five years and countless cups of chai later, we're writing our own story. Come celebrate it with us!",
        dress={"haldi": "Yellow ethnic 💛", "mehndi": "Green & bright colours", "sangeet": "Indo-western glam ✨",
               "wedding": "Traditional ethnic", "reception": "Formal: gowns & suits"},
    ),
    "hi": dict(
        style="north_indian", bride=("Ananya", "अनन्या"), groom=("Arjun", "अर्जुन"), city="Varanasi",
        venue="Ganga Mahal", address="Assi Ghat", home="Sharma Niwas", reception="Taj Ganges",
        hosts="शर्मा एवं मिश्रा परिवार", blessing_line="स्व. श्रीमती कमला देवी शर्मा के आशीर्वाद से",
        families=("श्रीमती एवं श्री राकेश शर्मा", "श्रीमती एवं श्री विनोद मिश्रा"), guest="शर्मा परिवार",
        functions=HINDU, hashtag="#AnanyaArjunKiShaadi", wish="दोनों को ढेर सारी शुभकामनाएँ! 🙏",
    ),
    "mr": dict(
        style="modern_minimal", bride=("Sayali", "सायली"), groom=("Aditya", "आदित्य"), city="Pune",
        venue="Shrimant Lawns", address="Karve Nagar", home="Deshpande Wada", reception="Hotel Shreyas",
        hosts="देशपांडे व कुलकर्णी परिवार", blessing_line="कै. सौ. सुमन देशपांडे यांच्या आशीर्वादाने",
        families=("सौ. व श्री. विजय देशपांडे", "सौ. व श्री. प्रकाश कुलकर्णी"), guest="जोशी कुटुंब",
        functions=HINDU, hashtag="#SayaliAditya", wish="नवदांपत्यास हार्दिक शुभेच्छा! 🙏",
    ),
    "bn": dict(
        style="bengali", bride=("Rimjhim", "রিমঝিম"), groom=("Sourav", "সৌরভ"), city="Kolkata",
        venue="Nandan Banquet", address="Salt Lake", home="Chatterjee Bari", reception="ITC Royal Bengal",
        hosts="চট্টোপাধ্যায় ও মুখোপাধ্যায় পরিবার", blessing_line="স্বর্গীয়া কমলা দেবীর আশীর্বাদে",
        families=("শ্রীমতী ও শ্রী অমিত চট্টোপাধ্যায়", "শ্রীমতী ও শ্রী সুব্রত মুখোপাধ্যায়"), guest="বসু পরিবার",
        functions=["haldi", "wedding", "reception"], hashtag="#RimjhimSourav", wish="নবদম্পতিকে অনেক শুভেচ্ছা! 🙏",
    ),
    "gu": dict(
        style="mehndi", bride=("Dhvani", "ધ્વનિ"), groom=("Parth", "પાર્થ"), city="Ahmedabad",
        venue="Rajpath Club Lawns", address="SG Highway", home="Patel Niwas", reception="Hyatt Regency",
        hosts="પટેલ અને શાહ પરિવાર", blessing_line="સ્વ. શ્રીમતી કમળાબેન પટેલના આશીર્વાદથી",
        families=("શ્રીમતી અને શ્રી કિરીટભાઈ પટેલ", "શ્રીમતી અને શ્રી હિતેશભાઈ શાહ"), guest="મહેતા પરિવાર",
        functions=HINDU, hashtag="#DhvaniParth", wish="નવદંપતીને હાર્દિક શુભેચ્છા! 🙏",
    ),
    "pa": dict(
        style="haldi", bride=("Simran", "ਸਿਮਰਨ"), groom=("Harjot", "ਹਰਜੋਤ"), city="Amritsar",
        venue="Gurdwara Sahib, Ranjit Avenue", address="", home="Gill Kothi", reception="Hyatt Regency Amritsar",
        hosts="ਗਿੱਲ ਅਤੇ ਸੰਧੂ ਪਰਿਵਾਰ", blessing_line="ਸਵਰਗੀ ਸਰਦਾਰਨੀ ਕਮਲਜੀਤ ਕੌਰ ਜੀ ਦੀ ਅਸੀਸ ਨਾਲ",
        families=("ਸਰਦਾਰਨੀ ਅਤੇ ਸਰਦਾਰ ਗੁਰਪ੍ਰੀਤ ਸਿੰਘ ਗਿੱਲ", "ਸਰਦਾਰਨੀ ਅਤੇ ਸਰਦਾਰ ਮਨਜੀਤ ਸਿੰਘ ਸੰਧੂ"), guest="ਢਿੱਲੋਂ ਪਰਿਵਾਰ",
        functions=["haldi", "mehndi", "sangeet", "wedding", "reception"], hashtag="#SimranHarjot",
        wish="ਜੋੜੀ ਨੂੰ ਬਹੁਤ ਬਹੁਤ ਵਧਾਈਆਂ! 🙏",
    ),
    "ta": dict(
        style="south_indian", bride=("Meenakshi", "மீனாட்சி"), groom=("Karthik", "கார்த்திக்"), city="Madurai",
        venue="Sri Meenakshi Kalyana Mandapam", address="Anna Nagar", home="Subramaniam Illam", reception="Fortune Pandiyan",
        hosts="சுப்பிரமணியம் மற்றும் ராமநாதன் குடும்பத்தினர்", blessing_line="அமரர் திருமதி கமலா அம்மாள் அவர்களின் ஆசியுடன்",
        families=("திருமதி & திரு. சுப்பிரமணியம்", "திருமதி & திரு. ராமநாதன்"), guest="ஐயர் குடும்பம்",
        functions=SOUTH, hashtag="#MeenakshiKarthik", wish="மணமக்களுக்கு இனிய திருமண வாழ்த்துகள்! 🙏",
    ),
    "te": dict(
        style="south_indian", bride=("Lakshmi", "లక్ష్మి"), groom=("Venkat", "వెంకట్"), city="Hyderabad",
        venue="N Convention", address="Madhapur", home="Reddy Nivas", reception="Taj Falaknuma Palace",
        hosts="రెడ్డి మరియు రావు కుటుంబాలు", blessing_line="స్వర్గీయ శ్రీమతి కమలమ్మ గారి ఆశీస్సులతో",
        families=("శ్రీమతి & శ్రీ శ్రీనివాస రెడ్డి", "శ్రీమతి & శ్రీ రామారావు"), guest="శర్మ కుటుంబం",
        functions=SOUTH, hashtag="#LakshmiVenkat", wish="నూతన వధూవరులకు శుభాకాంక్షలు! 🙏",
    ),
    "kn": dict(
        style="modern_minimal", bride=("Divya", "ದಿವ್ಯಾ"), groom=("Pranav", "ಪ್ರಣವ್"), city="Mysuru",
        venue="Lalitha Mahal Palace", address="", home="Gowda Mane", reception="Radisson Blu Mysore",
        hosts="ಗೌಡ ಮತ್ತು ಹೆಗ್ಡೆ ಕುಟುಂಬ", blessing_line="ದಿವಂಗತ ಶ್ರೀಮತಿ ಕಮಲಮ್ಮ ಅವರ ಆಶೀರ್ವಾದದೊಂದಿಗೆ",
        families=("ಶ್ರೀಮತಿ ಮತ್ತು ಶ್ರೀ ರಮೇಶ್ ಗೌಡ", "ಶ್ರೀಮತಿ ಮತ್ತು ಶ್ರೀ ಸುರೇಶ್ ಹೆಗ್ಡೆ"), guest="ರಾವ್ ಕುಟುಂಬ",
        functions=SOUTH, hashtag="#DivyaPranav", wish="ನವದಂಪತಿಗಳಿಗೆ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು! 🙏",
    ),
    "ml": dict(
        style="christian", bride=("Anna", "അന്ന"), groom=("Joseph", "ജോസഫ്"), city="Kochi",
        venue="St. Mary's Basilica", address="Ernakulam", home="Puthenpurackal House", reception="Grand Hyatt Kochi",
        hosts="പുത്തൻപുരയ്ക്കൽ & കളത്തിൽ കുടുംബങ്ങൾ", blessing_line="പരേതയായ ശ്രീമതി മറിയാമ്മയുടെ അനുഗ്രഹത്തോടെ",
        families=("ശ്രീമതി & ശ്രീ തോമസ് പുത്തൻപുരയ്ക്കൽ", "ശ്രീമതി & ശ്രീ മാത്യു കളത്തിൽ"), guest="മാത്യു കുടുംബം",
        functions=["engagement", "wedding", "reception"], hashtag="#AnnaWedsJoseph",
        wish="നവദമ്പതികൾക്ക് ഹൃദയം നിറഞ്ഞ ആശംസകൾ! 🙏",
    ),
}

# Other guests, to make the family console look lived-in. name, side, functions, reply, people, food
OTHER_GUESTS = [
    ("Meena Bua & Family", "bride", ["haldi", "mehndi", "wedding"], "yes", 4, "veg"),
    ("Rahul & Sneha", "groom", ["sangeet", "wedding", "reception"], "yes", 2, "jain"),
    ("Verma Uncle", "groom", ["wedding", "reception"], "maybe", 3, "veg"),
    ("Dr. Iyer", "groom", ["reception"], "no", 0, ""),
]


def demo_order(lang: str = "en") -> Order | None:
    with SessionLocal() as db:
        return db.scalar(select(Order).where(Order.source == "demo", Order.language == lang))


def _schedule(cfg: dict, day: date) -> list[dict]:
    offsets = {"engagement": -3, "haldi": -2, "mehndi": -2, "sangeet": -1, "wedding": 0, "reception": 1}
    times = {"engagement": "18:00", "haldi": "10:00", "mehndi": "16:00", "sangeet": "19:30", "wedding": "19:30", "reception": "20:00"}
    venues = {"haldi": cfg["home"], "mehndi": cfg["home"], "reception": cfg["reception"]}
    if cfg["style"] in ("south_indian", "christian"):
        times["wedding"] = "09:30"  # morning muhurtham / church service
    return [
        {"key": k, "date": (day + timedelta(days=offsets[k])).isoformat(), "time": times[k], "venue": venues.get(k, "")}
        for k in cfg["functions"]
    ]


def _create(lang: str, cfg: dict) -> int:
    day = date.today() + timedelta(days=60)
    with SessionLocal() as db:
        order = Order(
            public_id=orders.new_public_id(db), token=new_token(), status=OrderStatus.QUEUED.value, source="demo",
            customer_name="Demo", phone="910000000000",
            bride_name=cfg["bride"][0], groom_name=cfg["groom"][0],
            bride_name_local=cfg["bride"][1], groom_name_local=cfg["groom"][1],
            bride_family=cfg["families"][0], groom_family=cfg["families"][1],
            wedding_date=day, venue_name=cfg["venue"], venue_address=cfg["address"], city=cfg["city"],
            language=lang, style=cfg["style"], package="premium", addons=[], functions=_schedule(cfg, day),
            referral_code=orders.new_referral_code(db, "demo"), total=0, amount_paid=0,
        )
        db.add(order)
        db.flush()
        db.add(EventDetails(
            order_id=order.id, hosts=cfg["hosts"], hashtag=cfg["hashtag"], blessing_line=cfg["blessing_line"],
            story=cfg.get("story", ""), dress_codes=cfg.get("dress", {}), upi_id="demo@upi",
        ))
        available = set(cfg["functions"])
        guests = [(cfg["guest"], "bride", [], "", 0, "")] + OTHER_GUESTS
        for n, (name, side, fns, reply, people, food) in enumerate(guests):
            fns = [f for f in fns if f in available]
            db.add(Invitee(
                order_id=order.id, code=invites.new_code(db), name=name, side=side, functions=fns,
                attending=reply, headcount=people, attending_functions=fns if reply in ("yes", "maybe") else [],
                food=food, message=cfg["wish"] if n == 1 else "", sent_at=utcnow(),
                opened_at=utcnow() if reply else None, open_count=2 if reply else 0,
                responded_at=utcnow() if reply else None,
            ))
            db.flush()
        db.commit()
        return order.id


CUSTOM_PHOTO_DIR = APP_DIR / "static" / "demo"  # optional: static/demo/<lang>/<role>.jpg or static/demo/<role>.jpg


def _custom_photo(lang: str, role: str) -> tuple[bytes, bool] | None:
    """(bytes, ready) for your own photo. `<role>.ready.jpg` is used as-is; `<role>.jpg` gets enhanced."""
    for folder in (CUSTOM_PHOTO_DIR / lang, CUSTOM_PHOTO_DIR):
        for name, ready in ((f"{role}.ready.jpg", True), (f"{role}.jpg", False)):
            if (folder / name).exists():
                return (folder / name).read_bytes(), ready
    return None


def ensure_demo_portraits() -> None:
    """Give every demo wedding bride, groom and family portraits: your photos from static/demo
    when present (re-applied whenever the file changes), otherwise illustrated regional portraits."""
    import hashlib

    from app.services import demo_art

    for lang in DEMOS:
        order_ref = demo_order(lang)
        if order_ref is None:
            continue
        with SessionLocal() as db:
            order = db.get(Order, order_ref.id)
            current = invites.portraits(order)
            changed = []
            for role in ("bride", "groom", "family"):
                custom = _custom_photo(lang, role)
                if custom:
                    data, ready = custom
                    digest = hashlib.sha1(data).hexdigest()[:12]
                    if (current.get(role) and (current[role].meta or {}).get("source") == digest):
                        continue
                    invites.save_portrait(db, order, role, data, enhance=not ready, vibrant=True, meta={"source": digest})
                    changed.append(role)
                elif role not in current or (current[role].meta or {}).get("source"):
                    svg, w, h = demo_art.portrait_svg(demo_art.LANG_REGION.get(lang, "north"), role)
                    data = demo_art.render_png(svg, w, h)
                    if data:
                        invites.save_portrait(db, order, role, data, enhance=False)
                        changed.append(role)
            if changed:
                db.commit()
                log.info("demo portraits updated: %s %s", lang, changed)


def ensure_demo() -> None:
    """Create any missing demo weddings (one per language), with real generated cards."""
    for lang, cfg in DEMOS.items():
        if demo_order(lang):
            continue
        order_id = _create(lang, cfg)
        pipeline.run_order(order_id)
        with SessionLocal() as db:
            order = db.get(Order, order_id)
            order.status = OrderStatus.DELIVERED.value
            order.delivered_at = utcnow()
            db.commit()
        log.info("demo wedding created: %s", lang)
    ensure_demo_portraits()
