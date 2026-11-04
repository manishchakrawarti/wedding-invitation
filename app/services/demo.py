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

# --- everything the create page offers, shown in the live demos ------------------------------------------
# degrees and home towns under the names, the welcoming relatives, the children's line, contacts (names only:
# a sample number could belong to a real person), a gift note, and dress codes in the card's language.
DEMO_EXTRAS: dict[str, dict] = {
    "en": dict(degrees=("B.Tech · Software Engineer", "MBA · Chartered Accountant"), homes=("Malviya Nagar, Jaipur", "C-Scheme, Jaipur"),
               welcomers="Dada-Dadi, Chacha-Chachi, Mama-Mami, Bua-Phupha and the entire Sharma & Mehta families",
               kids_note="Didi ki shaadi mein zaroor aana! — Aarav & Myra", contacts=("Rakesh Sharma (Papa)", "Rohit Sharma (Bhaiya)"),
               sender="Rakesh Sharma"),
    "hi": dict(degrees=("एम.बी.बी.एस. (डॉक्टर)", "बी.टेक (इंजीनियर)"), homes=("अस्सी, वाराणसी", "लंका, वाराणसी"),
               welcomers="दादा-दादी, चाचा-चाची, मामा-मामी, बुआ-फूफा एवं समस्त शर्मा परिवार",
               kids_note="मेरी दीदी की शादी में ज़रूर आना! — आरव, मायरा", contacts=("राकेश शर्मा (पापा)", "रोहित शर्मा (भैया)"),
               sender="राकेश शर्मा",
               dress={"haldi": "पीले परिधान 💛", "mehndi": "हरे और चटक रंग", "sangeet": "इंडो-वेस्टर्न ✨", "wedding": "पारंपरिक परिधान",
                      "reception": "फ़ॉर्मल"}),
    "mr": dict(degrees=("बी.ई. (अभियंता)", "एम.बी.ए."), homes=("कोथरूड, पुणे", "सदाशिव पेठ, पुणे"),
               welcomers="आजी-आजोबा, काका-काकू, मामा-मामी आणि समस्त देशपांडे कुटुंब",
               kids_note="माझ्या ताईच्या लग्नाला नक्की या! — आर्या, ओम", contacts=("विजय देशपांडे (बाबा)", "ओंकार देशपांडे (दादा)"),
               sender="विजय देशपांडे",
               dress={"haldi": "पिवळे कपडे 💛", "mehndi": "हिरवा रंग", "sangeet": "इंडो-वेस्टर्न ✨", "wedding": "पारंपरिक नऊवारी / फेटा",
                      "reception": "फॉर्मल"}),
    "bn": dict(degrees=("এম.বি.বি.এস.", "বি.টেক"), homes=("সল্টলেক, কলকাতা", "বেহালা, কলকাতা"),
               welcomers="ঠাকুমা-দাদু, কাকা-কাকিমা ও সমস্ত চট্টোপাধ্যায় পরিবার", kids_note="দিদির বিয়েতে অবশ্যই এসো! — ঋজু, তিন্নি",
               contacts=("অমিত চট্টোপাধ্যায় (বাবা)", "রাহুল (দাদা)"), sender="অমিত চট্টোপাধ্যায়"),
    "gu": dict(degrees=("સી.એ.", "એમ.બી.એ."), homes=("નવરંગપુરા, અમદાવાદ", "સેટેલાઇટ, અમદાવાદ"),
               welcomers="દાદા-દાદી, કાકા-કાકી, મામા-મામી અને સમસ્ત પટેલ પરિવાર", kids_note="દીદીના લગ્નમાં જરૂર આવજો! — આરવ, ક્રિશા",
               contacts=("કિરીટભાઈ પટેલ (પપ્પા)", "હર્ષ પટેલ (ભાઈ)"), sender="કિરીટભાઈ પટેલ"),
    "pa": dict(degrees=("ਬੀ.ਟੈੱਕ", "ਐੱਮ.ਬੀ.ਏ."), homes=("ਰਣਜੀਤ ਐਵੇਨਿਊ, ਅੰਮ੍ਰਿਤਸਰ", "ਮਾਡਲ ਟਾਊਨ, ਜਲੰਧਰ"),
               welcomers="ਦਾਦਾ-ਦਾਦੀ, ਚਾਚਾ-ਚਾਚੀ, ਮਾਮਾ-ਮਾਮੀ ਅਤੇ ਸਮੂਹ ਗਿੱਲ ਪਰਿਵਾਰ", kids_note="ਦੀਦੀ ਦੇ ਵਿਆਹ ਵਿੱਚ ਜ਼ਰੂਰ ਆਉਣਾ! — ਗੁਰਨੂਰ, ਜੈਵੀਰ",
               contacts=("ਗੁਰਪ੍ਰੀਤ ਸਿੰਘ ਗਿੱਲ (ਪਾਪਾ)", "ਅਮਨ (ਵੀਰ ਜੀ)"), sender="ਗੁਰਪ੍ਰੀਤ ਸਿੰਘ ਗਿੱਲ"),
    "ta": dict(degrees=("பி.இ.", "எம்.பி.ஏ."), homes=("அண்ணா நகர், மதுரை", "கே.கே. நகர், மதுரை"),
               welcomers="தாத்தா-பாட்டி, சித்தப்பா-சித்தி மற்றும் சுப்பிரமணியம் குடும்பத்தினர்", kids_note="அக்கா கல்யாணத்துக்கு கண்டிப்பா வாங்க! — ஆதவ், தியா",
               contacts=("சுப்பிரமணியம் (அப்பா)", "ராஜேஷ் (அண்ணா)"), sender="சுப்பிரமணியம்"),
    "te": dict(degrees=("ఎం.బి.బి.ఎస్.", "బి.టెక్"), homes=("జూబ్లీ హిల్స్, హైదరాబాద్", "కూకట్‌పల్లి, హైదరాబాద్"),
               welcomers="తాతయ్య-నానమ్మ, బాబాయి-పిన్ని మరియు రెడ్డి కుటుంబ సభ్యులు", kids_note="అక్క పెళ్లికి తప్పకుండా రండి! — ఆద్య, విహాన్",
               contacts=("శ్రీనివాస రెడ్డి (నాన్న)", "కిరణ్ (అన్నయ్య)"), sender="శ్రీనివాస రెడ్డి"),
    "kn": dict(degrees=("ಬಿ.ಇ.", "ಎಂ.ಬಿ.ಎ."), homes=("ಸರಸ್ವತಿಪುರಂ, ಮೈಸೂರು", "ಜಯನಗರ, ಬೆಂಗಳೂರು"),
               welcomers="ಅಜ್ಜ-ಅಜ್ಜಿ, ಚಿಕ್ಕಪ್ಪ-ಚಿಕ್ಕಮ್ಮ ಮತ್ತು ಗೌಡ ಕುಟುಂಬದವರು", kids_note="ಅಕ್ಕನ ಮದುವೆಗೆ ಖಂಡಿತ ಬನ್ನಿ! — ಅನ್ವಿ, ಆರುಷ್",
               contacts=("ರಮೇಶ್ ಗೌಡ (ಅಪ್ಪ)", "ಸಂದೀಪ್ (ಅಣ್ಣ)"), sender="ರಮೇಶ್ ಗೌಡ"),
    "ml": dict(degrees=("എം.ബി.ബി.എസ്.", "ബി.ടെക്"), homes=("കടവന്ത്ര, കൊച്ചി", "പാലാ, കോട്ടയം"),
               welcomers="വല്യപ്പച്ചൻ, വല്യമ്മച്ചി, മറ്റ് ബന്ധുക്കൾ എന്നിവർ", kids_note="ചേച്ചിയുടെ കല്യാണത്തിന് ഉറപ്പായും വരണേ! — ആൻ, ജോയൽ",
               contacts=("തോമസ് (പപ്പ)", "ജിതിൻ (ചേട്ടൻ)"), sender="തോമസ്"),
}

EVENT_EXTRAS: dict[str, dict] = {  # by category, with a few occasions overridden below
    "birthday": dict(welcomers="Grandparents, cousins and all our friends", contacts=("Neha Sharma (Mummy)",), gift_note=""),
    "anniversary": dict(blessing_line="With the blessings of our elders", welcomers="Their children, grandchildren and the whole family",
                        kids_note="Come celebrate Mummy-Papa's big day! — Riya & Kabir", contacts=("Kabir (Son)",), gift_note="blessings_only"),
    "puja": dict(blessing_line="With the blessings of Lord Ganesha and our elders", welcomers="The Sharma family and all our relatives",
                 contacts=("Rakesh Sharma",), gift_note="blessings_only", dress="Traditional"),
    "baby": dict(blessing_line="With the blessings of Dada-Dadi and Nana-Nani", welcomers="Grandparents, uncles, aunts and cousins",
                 kids_note="Come meet me! I can't wait to see you 👶", contacts=("Rohan (Papa)",), gift_note="no_boxed"),
    "festival": dict(welcomers="Family, neighbours and friends", contacts=("The hosts",), gift_note="blessings_only"),
    "corporate": dict(contacts=("Events team",), gift_note=""),
}
TYPE_EXTRAS: dict[str, dict] = {
    "kids_birthday": dict(kids_note="Please come to my party! There will be cake 🎂 — Aarav", dress="Superheroes & princesses welcome"),
    "milestone_birthday": dict(blessing_line="With love from his children and grandchildren",
                               kids_note="Come celebrate Dadu's 60th! — the grandchildren"),
    "theme_party": dict(dress="Bollywood glam ✨"),
    "kitty_party": dict(dress="Retro glam 💃"),
    "christmas_newyear": dict(dress="Red, green or a little sparkle 🎄"),
    "lohri_sankranti": dict(dress="Punjabi traditional"),
    "eid_dawat": dict(blessing_line="", dress="Festive ethnic"),
    "chhath_puja": dict(blessing_line="Jai Chhathi Maiya 🙏 With the blessings of Surya Dev",
                        welcomers="Dadi Maa (vratee), Chacha-Chachi and the entire Singh family",
                        kids_note="Ghat pe zaroor aana, thekua milega! — Anshu & Pihu", contacts=("Manoj Singh",),
                        dress="Traditional: saree, kurta-dhoti", sender="The Singh family"),
    "family_reunion": dict(kids_note="Can't wait to play with all my cousins! — Myra"),
}


def _set_extras(db, order: Order, extras: dict, dress: dict | None = None) -> None:
    ev = invites.event_details(db, order)
    for field in ("welcomers", "kids_note", "gift_note"):
        if field in extras:
            setattr(ev, field, extras[field])
    if "blessing_line" in extras:
        ev.blessing_line = extras["blessing_line"]
    ev.rsvp_contacts = [{"name": n, "phone": ""} for n in extras.get("contacts", ())]
    if dress:
        ev.dress_codes = {**(ev.dress_codes or {}), **dress}
    sender = extras.get("sender", "")
    for invitee in order.invitees:
        invitee.sent_by = sender


def enrich_demos() -> None:
    """Fill the live demos with everything the create page offers (safe to repeat: always the latest content)."""
    from app import events

    with SessionLocal() as db:
        for order in db.scalars(select(Order).where(Order.source == "demo")).all():
            if order.is_wedding:
                x = DEMO_EXTRAS.get(order.language)
                if not x:
                    continue
                order.bride_degree, order.groom_degree = x["degrees"]
                order.bride_home, order.groom_home = x["homes"]
                _set_extras(db, order, {**x, "gift_note": x.get("gift_note", "blessings_only")}, x.get("dress"))
            else:
                t = events.TYPES.get(order.event_type)
                if t is None:
                    continue
                x = {**EVENT_EXTRAS.get(t.category, {}), **TYPE_EXTRAS.get(order.event_type, {})}
                if "sender" not in x:
                    x["sender"] = "The Sharma family" if t.category not in ("corporate", "festival") else ""
                dress = {order.event_type: x["dress"]} if x.get("dress") else None
                _set_extras(db, order, x, dress)
        db.commit()

# Other guests, to make the family console look lived-in. name, side, functions, reply, people, food
OTHER_GUESTS = [
    ("Meena Bua & Family", "bride", ["haldi", "mehndi", "wedding"], "yes", 4, "veg"),
    ("Rahul & Sneha", "groom", ["sangeet", "wedding", "reception"], "yes", 2, "jain"),
    ("Verma Uncle", "groom", ["wedding", "reception"], "maybe", 3, "veg"),
    ("Dr. Iyer", "groom", ["reception"], "no", 0, ""),
]


def demo_order(lang: str = "en", event: str = "wedding") -> Order | None:
    with SessionLocal() as db:
        return db.scalar(select(Order).where(Order.source == "demo", Order.language == lang, Order.event_type == event))


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
    ensure_event_demos()
    ensure_demo_portraits()
    ensure_event_portraits()
    enrich_demos()
    refresh_demo_designs()


def refresh_demo_designs() -> None:
    """Redraw demo cards made with an older card design (overlay.CARD_DESIGN) so the live samples show the
    current look. Only the text is redrawn, over the existing artwork, so it costs nothing."""
    from app.services.overlay import CARD_DESIGN

    redrawn = 0
    with SessionLocal() as db:
        for order in db.scalars(select(Order).where(Order.source == "demo")).all():
            if any((a.meta or {}).get("design", 1) < CARD_DESIGN for a in order.live_assets("final")):
                redrawn += bool(pipeline.redraw_text(db, order))
    if redrawn:
        log.info("redrew %d demo invitation(s) with card design %d", redrawn, CARD_DESIGN)


# --- demos for every other occasion (English) ------------------------------------
EVENT_VENUES = {
    "birthday": ("Funky Monkeys Party Hall", "Koregaon Park", "Pune"),
    "anniversary": ("The Taj Lawns", "Colaba", "Mumbai"),
    "puja": ("Sharma Niwas", "Sector 15", "Gurugram"),
    "baby": ("Mehta Residence", "Satellite", "Ahmedabad"),
    "festival": ("Community Clubhouse", "Indiranagar", "Bengaluru"),
    "corporate": ("Hotel Grand Hyatt Ballroom", "BKC", "Mumbai"),
}
TYPE_VENUES = {"chhath_puja": ("Gandhi Ghat", "Ashok Rajpath", "Patna")}  # Chhath is offered at a ghat
TYPE_TIMES = {"chhath_puja": "17:00"}  # Sandhya Arghya, at sunset
EVENT_WISHES = {
    "birthday": "Happy birthday! Can't wait to celebrate with you 🎉",
    "anniversary": "Congratulations on this beautiful milestone! ❤️",
    "puja": "Jai Shri Ram 🙏 We'll be there for the blessings.",
    "baby": "So much love to the little one and the family! 🌸",
    "festival": "Can't wait for the celebrations! 🎊",
    "corporate": "Looking forward to it. Congratulations to the whole team!",
}


def _demo_hashtag(t) -> str:
    """'#AaravBirthdayParty', '#SunitaVijaySilverJubilee', '#ShreeJewellersGrandOpening'."""
    import re

    from app import events

    skip = {"the", "family", "shri", "baby", "of", "and"}
    headline = (events.jubilee(t.demo[2]) or (t.headline,))[0] if t.key == "milestone_anniversary" else t.headline
    names = [w for w in re.findall(r"[A-Za-z0-9]+", f"{t.demo[0]} {t.demo[1]}") if w.lower() not in skip][:2]
    head = [w for w in re.findall(r"[A-Za-z0-9]+", headline) if w.lower() not in skip][:2]
    return "#" + "".join(w[:1].upper() + w[1:] for w in names + head)


def ensure_event_demos() -> None:
    """One live demo per event type, with guests, RSVPs and generated cards."""
    from app import events

    day = date.today() + timedelta(days=45)
    for key, t in events.TYPES.items():
        existing = demo_order("en", key)
        if existing:
            with SessionLocal() as db:  # keep older demos' hashtags up to date
                ev = db.get(Order, existing.id).event
                if ev and ev.hashtag != _demo_hashtag(t):
                    ev.hashtag = _demo_hashtag(t)
                    db.commit()
            continue
        primary, secondary, detail = t.demo
        venue, address, city = TYPE_VENUES.get(key) or EVENT_VENUES[t.category]
        with SessionLocal() as db:
            order = Order(
                public_id=orders.new_public_id(db), token=new_token(), status=OrderStatus.QUEUED.value, source="demo",
                customer_name="Demo", phone="910000000000", bride_name=primary, groom_name=secondary,
                wedding_date=day, venue_name=venue, venue_address=address, city=city, language="en",
                style=t.styles[0], package="premium", addons=[], event_type=key, occasion_detail=detail,
                functions=[{"key": key, "label": t.headline, "label_hi": t.headline_hi, "date": day.isoformat(),
                            "time": TYPE_TIMES.get(key) or ("10:00" if t.category == "puja" else "19:00"), "venue": ""}],
                referral_code=orders.new_referral_code(db, "demo"), total=0, amount_paid=0,
            )
            db.add(order)
            db.flush()
            hosts = "" if t.category in ("puja", "festival", "corporate") else "The Sharma family"
            db.add(EventDetails(order_id=order.id, hosts=hosts, dress_codes={}, upi_id="demo@upi", hashtag=_demo_hashtag(t)))
            for n, (name, side, _fns, reply, people, food) in enumerate([("Mehta Family", "", [], "", 0, "")] + OTHER_GUESTS):
                db.add(Invitee(
                    order_id=order.id, code=invites.new_code(db), name=name, side="", functions=[],
                    attending=reply, headcount=people, attending_functions=[key] if reply in ("yes", "maybe") else [],
                    food=food, message=EVENT_WISHES[t.category] if n == 1 else "", sent_at=utcnow(),
                    opened_at=utcnow() if reply else None, open_count=2 if reply else 0,
                    responded_at=utcnow() if reply else None,
                ))
                db.flush()
            db.commit()
            order_id = order.id
        pipeline.run_order(order_id)
        with SessionLocal() as db:
            order = db.get(Order, order_id)
            order.status = OrderStatus.DELIVERED.value
            order.delivered_at = utcnow()
            db.commit()
        log.info("event demo created: %s", key)


def ensure_event_portraits() -> None:
    """Illustrated people for event demos (birthday child, couple, family…); none for corporate events."""
    from app import events
    from app.catalog import STYLES
    from app.services import demo_art

    for key in events.TYPES:
        ref = demo_order("en", key)
        if ref is None:
            continue
        with SessionLocal() as db:
            order = db.get(Order, ref.id)
            have = set(invites.portraits(order))
            st = STYLES[order.style]
            bg = ("#%02x%02x%02x" % tuple(min(255, c + 60) for c in st.bg_top), "#%02x%02x%02x" % st.bg_top)
            added = []
            for role in ("bride", "groom", "family"):
                if role in have:
                    continue
                art = demo_art.event_portrait_svg(key, role, bg)
                data = demo_art.render_png(*art) if art else None
                if data:
                    invites.save_portrait(db, order, role, data, enhance=False)
                    added.append(role)
            if added:
                db.commit()
