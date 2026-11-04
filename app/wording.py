"""Invitation wording library: ready messages in Hindi and English for every occasion, to copy, send on
WhatsApp or put on a card. One page per occasion (/wording/griha-pravesh-invitation-message…).

Placeholders in [square brackets] are for the family to replace; the page highlights them."""
from dataclasses import dataclass
from functools import lru_cache

from app import events, seo

# --- shared by every occasion in a category ({event} = the occasion's name) ------------------------------
CATEGORY = {
    "birthday": {
        "hi": ["आपको सपरिवार [नाम] के जन्मदिन समारोह में सादर आमंत्रित करते हैं। आपकी उपस्थिति हमारी ख़ुशी दोगुनी कर देगी। 🎂\n📅 [तारीख़] · ⏰ [समय]\n📍 [स्थान]",
               "केक, मस्ती और ढेर सारी यादें! 🎈 [नाम] का जन्मदिन है, आप ज़रूर आइए।\n[तारीख़], [समय] · [स्थान]",
               "हमारे घर की रौनक [नाम] का जन्मदिन है। आइए, आशीर्वाद दीजिए और जश्न में शामिल होइए। 🙏"],
        "en": ["You're invited to celebrate [Name]'s birthday! 🎂 Join us for cake, fun and lots of memories.\n📅 [Date] · ⏰ [Time]\n📍 [Venue]",
               "It's party time! 🎉 Please join us as [Name] turns [Age].\n[Date] at [Time], [Venue]. See you there!",
               "Your presence is the best gift. Come and bless [Name] on their birthday. 💛\n[Date] · [Venue]"],
    },
    "anniversary": {
        "hi": ["[वर्ष] वर्षों का साथ, अनगिनत यादें। 💞 [नाम] एवं [नाम] की विवाह वर्षगाँठ पर आप सपरिवार सादर आमंत्रित हैं।\n📅 [तारीख़] · 📍 [स्थान]",
               "प्यार और साथ के [वर्ष] सुनहरे साल! आइए, इस ख़ुशी के मौक़े पर हमारे साथ जश्न मनाइए। 🥂",
               "माता-पिता की [वर्ष]वीं वर्षगाँठ पर आपका आशीर्वाद ही हमारे लिए सबसे बड़ा उपहार होगा। 🙏"],
        "en": ["[Years] years of love and laughter! 💞 Please join us to celebrate the anniversary of [Name] & [Name].\n📅 [Date] · 📍 [Venue]",
               "Celebrating a love that grows stronger every year. Join us for dinner and blessings on [Date] at [Venue]. 🥂",
               "Our parents are celebrating [Years] beautiful years together, and we'd love you to be there. Your blessings are the only gift we need. 🙏"],
    },
    "puja": {
        "hi": ["॥ श्री गणेशाय नमः ॥\nआपको सपरिवार हमारे निवास पर आयोजित [पूजा] में सादर आमंत्रित करते हैं। कृपया पधारकर प्रसाद ग्रहण करें। 🙏\n📅 [तारीख़] · ⏰ [समय]\n📍 [पता]",
               "प्रभु की कृपा से हमारे घर [पूजा] का आयोजन किया जा रहा है। आपकी उपस्थिति प्रार्थनीय है। 🪔\nपूजा: [समय] · आरती एवं प्रसाद: [समय]",
               "आइए, भक्ति और आशीर्वाद के इस पावन अवसर पर हमारे साथ जुड़िए। भोजन प्रसाद की व्यवस्था है। 🙏"],
        "en": ["With the blessings of the Almighty, we invite you and your family to the [Puja] at our home. Kindly join us and take prasad. 🙏\n📅 [Date] · ⏰ [Time]\n📍 [Address]",
               "Please join us for the [Puja], followed by aarti and prasad. Your presence will make the occasion complete. 🪔\n[Date], [Time] · [Address]",
               "We are blessed to host a [Puja] at our home on [Date]. Do come with your family and seek the blessings. 🙏"],
    },
    "baby": {
        "hi": ["हमारे घर नन्हे मेहमान की ख़ुशी में [समारोह] का आयोजन किया गया है। आप सपरिवार पधारकर आशीर्वाद दें। 👶\n📅 [तारीख़] · 📍 [स्थान]",
               "नन्हे क़दम, बड़ी ख़ुशियाँ! [नाम] के [समारोह] में आपका स्वागत है। 🌸",
               "बड़ों का आशीर्वाद और अपनों का प्यार: बस यही चाहिए। आइए, [समारोह] में शामिल होइए। 🙏"],
        "en": ["Tiny feet, big joy! 👶 Please join us for [Name]'s [Ceremony] and shower your blessings.\n📅 [Date] · 📍 [Venue]",
               "Our little one is ready to meet you! Join us for the [Ceremony] on [Date] at [Venue]. 🌸",
               "With hearts full of joy, we invite you to bless our baby at the [Ceremony]. Lunch to follow. 🙏"],
    },
    "festival": {
        "hi": ["त्योहार की ख़ुशियाँ अपनों के साथ ही पूरी होती हैं! 🎊 [त्योहार] के अवसर पर आप सपरिवार सादर आमंत्रित हैं।\n📅 [तारीख़] · 📍 [स्थान]",
               "मिठाई, संगीत और मस्ती! आइए, इस [त्योहार] हमारे साथ जश्न मनाइए। 🎉",
               "आपकी उपस्थिति से ही हमारा उत्सव रोशन होगा। ज़रूर पधारिए। ✨"],
        "en": ["Festivals are better together! 🎊 You and your family are invited to our [Festival] celebration.\n📅 [Date] · 📍 [Venue]",
               "Good food, music and great company. Join us this [Festival] on [Date] at [Venue]! 🎉",
               "Come celebrate with us! Your presence will light up our [Festival]. ✨"],
    },
    "corporate": {
        "hi": ["आपको [कंपनी] के [कार्यक्रम] में सादर आमंत्रित करते हैं। आपकी उपस्थिति हमारे लिए गौरव की बात होगी।\n📅 [तारीख़] · ⏰ [समय] · 📍 [स्थान]",
               "नई शुरुआत, आपके आशीर्वाद के साथ! [कंपनी] के [कार्यक्रम] में अवश्य पधारें। 🎊",
               "मुख्य अतिथि: [नाम]। आपकी उपस्थिति प्रार्थनीय है।"],
        "en": ["[Company] cordially invites you to the [Event].\n📅 [Date] · ⏰ [Time]\n📍 [Venue]\nWe look forward to welcoming you.",
               "A new chapter begins, and we'd love you to be part of it! Join us for the [Event] of [Company] on [Date]. 🎊",
               "In the gracious presence of our chief guest [Name], we request the pleasure of your company at the [Event]. RSVP: [Phone]"],
    },
}

# --- occasion-specific lines (added on top of the category's) --------------------------------------------
SPECIFIC = {
    "kids_birthday": {
        "hi": ["हमारा नन्हा [नाम] [उम्र] साल का हो रहा है! 🎈 गुब्बारे, केक और खेल: बच्चों के साथ ज़रूर आइए।"],
        "en": ["Balloons, cake and games! 🎈 Our little [Name] is turning [Age]. Bring the kids and join the fun!",
               "Superheroes, princesses and party animals welcome! 🦸 [Name]'s [Age]th birthday bash, [Date] at [Venue]."],
    },
    "milestone_birthday": {
        "hi": ["[नाम] जी के [उम्र]वें जन्मदिन के शुभ अवसर पर आप सपरिवार सादर आमंत्रित हैं। उनके आशीर्वाद के साथ यह दिन मनाइए। 🙏"],
        "en": ["[Age] years of wisdom, love and laughter! Join us to celebrate [Name]'s [Age]th birthday. 🎂",
               "A milestone worth celebrating: [Name] turns [Age]! Dinner and celebrations on [Date] at [Venue]."],
    },
    "theme_party": {
        "hi": ["थीम: [थीम]! 🥳 तैयार होकर आइए और पार्टी की रौनक बढ़ाइए।"],
        "en": ["Dress code: [Theme]! 🥳 Get ready for a night to remember on [Date] at [Venue].",
               "Lights, music, [Theme]! You're invited to the party of the year. 🎶"],
    },
    "milestone_anniversary": {
        "hi": ["विवाह की [रजत/स्वर्ण] जयंती! [वर्ष] वर्षों के अटूट साथ का उत्सव मनाने आप सपरिवार पधारें। 💐"],
        "en": ["A Silver/Golden Jubilee: [Years] years of togetherness! Join us as we honour [Name] & [Name]. 💐"],
    },
    "satyanarayan_puja": {
        "hi": ["श्री सत्यनारायण भगवान की कृपा से हमारे निवास पर श्री सत्यनारायण कथा एवं पूजन का आयोजन है। आप सपरिवार पधारकर कथा श्रवण करें एवं प्रसाद ग्रहण करें। 🙏",
               "पूर्णिमा के पावन अवसर पर श्री सत्यनारायण कथा। समय: [समय], आरती एवं प्रसाद के बाद भोजन।"],
        "en": ["By the grace of Lord Satyanarayan, we are holding the Satyanarayan Katha at our home. Please join us with your family for the puja and prasad. 🙏"],
    },
    "griha_pravesh": {
        "hi": ["ईश्वर की कृपा से हमने अपने नए घर में प्रवेश करने का निश्चय किया है। गृह प्रवेश पूजा के शुभ अवसर पर आप सपरिवार सादर आमंत्रित हैं। 🏡🙏\n📅 [तारीख़] · मुहूर्त: [समय]\n📍 [नया पता]",
               "नया घर, नई शुरुआत! 🏡 आपके आशीर्वाद के बिना अधूरी है। गृह प्रवेश पूजा एवं भोजन में अवश्य पधारें।",
               "हमारे सपनों का घर अब तैयार है। आइए, गृह प्रवेश के शुभ मुहूर्त पर आशीर्वाद दीजिए। 🪔"],
        "en": ["We've found our new home and would love your blessings! 🏡 Please join us for the Griha Pravesh puja.\n📅 [Date] · Muhurat: [Time]\n📍 [New address]",
               "New home, new beginnings! 🏡 Join us for the housewarming puja and lunch on [Date].",
               "Our dream home is ready, and it's only complete with you in it. Do come for the Griha Pravesh on [Date] at [Time]. 🪔"],
    },
    "rudrabhishek": {
        "hi": ["हर हर महादेव! 🔱 हमारे निवास पर रुद्राभिषेक का आयोजन है। आप सपरिवार पधारकर भोलेनाथ का आशीर्वाद प्राप्त करें।"],
        "en": ["Har Har Mahadev! 🔱 We are holding a Rudrabhishek at our home on [Date]. Please join us for the puja and bhandara."],
    },
    "ganesh_chaturthi": {
        "hi": ["गणपति बप्पा मोरया! 🌺 इस वर्ष भी बप्पा हमारे घर पधार रहे हैं। दर्शन एवं आरती के लिए आप सपरिवार आमंत्रित हैं।"],
        "en": ["Ganpati Bappa Morya! 🌺 Bappa is coming home this year too. Join us for darshan, aarti and modaks on [Date]."],
    },
    "krishna_janmashtami": {
        "hi": ["नंद के आनंद भयो, जय कन्हैया लाल की! 🦚 जन्माष्टमी पर मध्यरात्रि आरती एवं प्रसाद के लिए पधारें।"],
        "en": ["Celebrate the birth of Lord Krishna with us! 🦚 Bhajans, midnight aarti and prasad on [Date] at [Venue]."],
    },
    "durga_puja": {
        "hi": ["जय माता दी! 🌺 नवरात्रि एवं दुर्गा पूजा के पावन अवसर पर आरती, गरबा और प्रसाद के लिए आप सपरिवार आमंत्रित हैं।"],
        "en": ["Jai Mata Di! 🌺 Join us for Navratri: aarti, garba and prasad on [Date] at [Venue]."],
    },
    "diwali_puja": {
        "hi": ["दीपों के इस पर्व पर माँ लक्ष्मी की कृपा आप पर बनी रहे। 🪔 दीपावली लक्ष्मी पूजन एवं रात्रि भोज में आप सपरिवार सादर आमंत्रित हैं।"],
        "en": ["May the festival of lights bring joy to your home! 🪔 Join us for Laxmi Puja, dinner and fireworks on [Date]."],
    },
    "chhath_puja": {
        "hi": ["जय छठी मइया! 🌅 छठ महापर्व के पावन अवसर पर संध्या अर्घ्य एवं उषा अर्घ्य में आप सपरिवार सादर आमंत्रित हैं।\n📅 [तारीख़] · 🌇 संध्या अर्घ्य: [समय]\n📍 [घाट का नाम]",
               "सूर्य देव और छठी मइया की कृपा आप पर बनी रहे। 🙏 खरना का प्रसाद ग्रहण करने और घाट पर अर्घ्य देने अवश्य पधारें।",
               "काँच ही बाँस के बहँगिया, बहँगी लचकत जाए… 🎶 इस छठ घाट पर साथ चलिए! ठेकुआ प्रसाद आपका इंतज़ार कर रहा है।"],
        "en": ["Jai Chhathi Maiya! 🌅 Please join us for Chhath Mahaparv: Sandhya Arghya at sunset on [Date] and Usha Arghya at sunrise.\n📍 [Ghat name]",
               "May Surya Dev and Chhathi Maiya bless your family. 🙏 Come for the Kharna prasad and join us at the ghat for the arghya.",
               "Thekua, songs and the setting sun: celebrate Chhath with us at [Ghat] on [Date]. 🌇"],
    },
    "sundar_kand": {
        "hi": ["जय श्री राम! 🙏 हमारे निवास पर श्री सुंदरकांड पाठ का आयोजन है। आप सपरिवार पधारकर पुण्य लाभ लें।"],
        "en": ["Jai Shri Ram! 🙏 Please join us for the Sundar Kand Path at our home on [Date], followed by prasad."],
    },
    "baby_shower": {
        "hi": ["ममता का यह सुंदर पल! 🌸 [नाम] की गोद भराई रस्म में आप सादर आमंत्रित हैं। आशीर्वाद देने अवश्य पधारें।"],
        "en": ["A little one is on the way! 🌸 Join us for [Name]'s baby shower (Godh Bharai) and shower her with blessings."],
    },
    "namakaran": {
        "hi": ["हमारे घर के नन्हे सदस्य के नामकरण संस्कार में आप सपरिवार आमंत्रित हैं। नाम के साथ आपका आशीर्वाद भी चाहिए। 👶"],
        "en": ["Our baby is getting a name! 👶 Join us for the Namkaran ceremony on [Date] and bless our little one."],
    },
    "annaprashan": {
        "hi": ["[नाम] का पहला अन्न! 🍚 अन्नप्राशन संस्कार के शुभ अवसर पर आप सपरिवार आमंत्रित हैं।"],
        "en": ["[Name]'s first rice! 🍚 Join us for the Annaprashan ceremony on [Date] at [Venue]."],
    },
    "mundan": {
        "hi": ["[नाम] के मुंडन संस्कार के शुभ अवसर पर आप सपरिवार सादर आमंत्रित हैं। आशीर्वाद देने अवश्य पधारें। 🙏"],
        "en": ["Please join us for [Name]'s Mundan ceremony on [Date] and bless our little one. 🙏"],
    },
    "upanayanam": {
        "hi": ["[नाम] के उपनयन संस्कार (जनेऊ) के पावन अवसर पर आप सपरिवार सादर आमंत्रित हैं। 🙏"],
        "en": ["We invite you to the Upanayanam (sacred thread ceremony) of [Name] on [Date]. Your blessings are requested. 🙏"],
    },
    "lohri_sankranti": {
        "hi": ["लोहड़ी दी लख-लख वधाइयाँ! 🔥 अलाव, रेवड़ी-मूँगफली और भांगड़ा: आप सपरिवार आमंत्रित हैं।"],
        "en": ["Happy Lohri! 🔥 Bonfire, rewri, gajak and bhangra. Join us on [Date] at [Venue]!"],
    },
    "eid_dawat": {
        "hi": ["ईद मुबारक! 🌙 ईद की दावत में आप सपरिवार तशरीफ़ लाएँ, हमें ख़ुशी होगी।"],
        "en": ["Eid Mubarak! 🌙 Please join us for an Eid dawat with family and friends on [Date] at [Venue]."],
    },
    "christmas_newyear": {
        "hi": ["क्रिसमस और नए साल की ख़ुशियाँ साथ मनाइए! 🎄 पार्टी में आप सपरिवार आमंत्रित हैं।"],
        "en": ["Ho ho ho! 🎄 Join us for a Christmas & New Year party: food, music and a gift exchange on [Date]."],
    },
    "kitty_party": {
        "hi": ["लेडीज़, तैयार हो जाइए! 💃 इस बार की किटी पार्टी की थीम है [थीम]।"],
        "en": ["Ladies, it's kitty time! 💃 Theme: [Theme]. See you on [Date] at [Venue]."],
    },
    "family_reunion": {
        "hi": ["बहुत दिन हो गए! 👨‍👩‍👧‍👦 पूरे परिवार के मिलन समारोह में आप ज़रूर आइए: पुरानी यादें, नई बातें।"],
        "en": ["It's been too long! 👨‍👩‍👧‍👦 The whole family is getting together on [Date] at [Venue]. Old stories, new memories."],
    },
    "grand_opening": {
        "hi": ["[दुकान/कंपनी] का भव्य उद्घाटन! 🎊 मुख्य अतिथि [नाम] के कर-कमलों द्वारा। आप सादर आमंत्रित हैं।"],
        "en": ["We're opening our doors! 🎊 Join us for the grand opening of [Business] on [Date] at [Time], inaugurated by [Name]."],
    },
    "annual_day": {
        "hi": ["[कंपनी] के वार्षिक दिवस समारोह में आपका स्वागत है। थीम: [थीम]। 🏆"],
        "en": ["Celebrating another great year! 🏆 You're invited to the [Company] Annual Day. Theme: [Theme]."],
    },
    "product_launch": {
        "hi": ["कुछ नया आ रहा है! 🚀 [कंपनी] के नए उत्पाद [उत्पाद] के लॉन्च पर आप सादर आमंत्रित हैं।"],
        "en": ["Something new is coming! 🚀 Be the first to see [Product] at its launch on [Date] at [Venue]."],
    },
}

WEDDING = {
    "hi": [
        "॥ श्री गणेशाय नमः ॥\nआप सपरिवार सादर आमंत्रित हैं\nहमारी सुपुत्री [वधू] (सुपुत्री श्रीमती एवं श्री [नाम]) एवं [वर] (सुपुत्र श्रीमती एवं श्री [नाम]) के शुभ विवाह के मंगल अवसर पर।\n📅 [तारीख़] · ⏰ [समय]\n📍 [स्थान]",
        "दो दिलों के मिलन और दो परिवारों के संगम के इस शुभ अवसर पर आपकी उपस्थिति प्रार्थनीय है। 💍\nविवाह: [तारीख़], [स्थान]",
        "भेज रहे हैं स्नेह निमंत्रण, प्रियवर तुम्हें बुलाने को।\nहे मानस के राजहंस, तुम भूल न जाना आने को॥\n[वधू] संग [वर] · [तारीख़]",
        "हल्दी, मेहंदी, संगीत और फेरे: हर रस्म में आपका साथ चाहिए। 🌼 [वधू] और [वर] के विवाह में ज़रूर पधारें।",
        "आपके आशीर्वाद से ही यह रिश्ता पूरा होगा। [वधू] एवं [वर] के शुभ विवाह में आप सपरिवार सादर आमंत्रित हैं। 🙏",
        "मंडप सजेगा, शहनाई बजेगी, और आप होंगे तो रौनक बढ़ेगी! 🎶 [तारीख़] को [स्थान] पर ज़रूर आइए।",
    ],
    "en": [
        "Together with their families, [Bride] & [Groom] request the pleasure of your company at their wedding.\n📅 [Date] · ⏰ [Time]\n📍 [Venue]",
        "Two hearts, one love, and a celebration we'd love you to be part of. 💍 Please join us for the wedding of [Bride] & [Groom] on [Date].",
        "Haldi, mehndi, sangeet and the pheras: every function is better with you there! 🌼 Join us to celebrate [Bride] & [Groom].",
        "With the blessings of our elders, we invite you to the wedding of our daughter [Bride] with [Groom]. Your presence is our greatest gift. 🙏",
        "Save the date! 💌 [Bride] & [Groom] are getting married on [Date] in [City]. Formal invitation to follow.",
        "We're getting married! 🎉 Come dance, eat and bless us at our wedding on [Date] at [Venue]. — [Bride] & [Groom]",
    ],
    "shayari": [
        "चाँद-सितारों से सजी है ये रात,\nआइए बनें इस ख़ुशी के हम-साथ। 🌙",
        "रिश्तों की डोर में बँधने चले हैं दो दिल,\nआपकी दुआओं से ही होगी ये मंज़िल। 💞",
        "शहनाई की गूँज, मेहंदी का रंग,\nअधूरी है ख़ुशी, आपके बिना संग। 🎶",
        "फूलों सी महके ये नई ज़िंदगी,\nआपकी उपस्थिति से बढ़ेगी हर ख़ुशी। 🌸",
    ],
}
SECTION_TITLES = {"hi": "हिंदी में निमंत्रण संदेश", "en": "Invitation messages in English", "shayari": "Wedding card shayari"}


@dataclass(frozen=True)
class WordingPage:
    slug: str
    name: str
    local_name: str
    category: str
    sections: tuple  # ((title, lang, [messages]), …)
    create_url: str
    landing: str  # the occasion's landing page path

    @property
    def path(self) -> str:
        return f"/wording/{self.slug}"

    @property
    def count(self) -> int:
        return sum(len(m) for _, _, m in self.sections)

    @property
    def title(self) -> str:
        return f"{self.name} Invitation Message in Hindi & English | Invite All"

    @property
    def description(self) -> str:
        return (f"{self.count} ready {self.name} invitation messages in Hindi and English: copy, send on WhatsApp, "
                f"or put them on a free invitation card in 60 seconds.")


@lru_cache(maxsize=1)
def pages() -> dict[str, WordingPage]:
    found = [WordingPage("wedding-invitation-message", "Wedding", "शादी के निमंत्रण संदेश", "wedding",
                         tuple((SECTION_TITLES[k], "hi" if k != "en" else "en", WEDDING[k]) for k in ("hi", "en", "shayari")),
                         "/create", f"/wedding-{seo.SUFFIX}")]
    for key, t in events.TYPES.items():
        base = seo.TYPE_SLUGS.get(key) or t.name.lower().replace("'", "").replace(" ", "-")
        spec, cat = SPECIFIC.get(key, {}), CATEGORY[t.category]
        sections = (
            (f"{t.headline_hi}: हिंदी में निमंत्रण संदेश", "hi", spec.get("hi", []) + cat["hi"]),
            (f"{t.name} invitation messages in English", "en", spec.get("en", []) + cat["en"]),
        )
        found.append(WordingPage(f"{base}-invitation-message", t.name, t.headline_hi, t.category, sections,
                                 f"/create?event={key}", f"/{base}-{seo.SUFFIX}"))
    return {p.slug: p for p in found}


def for_landing(path: str) -> WordingPage | None:
    return next((p for p in pages().values() if p.landing == path), None)


def marked(text: str):
    """The message as HTML with the [placeholders] highlighted, so it's clear what to replace."""
    import re

    from markupsafe import Markup, escape

    return Markup(re.sub(r"\[([^\]]+)\]", r'<mark>[\1]</mark>', str(escape(text))))
