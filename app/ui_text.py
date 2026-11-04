"""The website in Hindi: a हिन्दी / English switch in the header (remembered in a cookie, or ?ui=hi in a link).

Pages are written in English; when Hindi is chosen, each finished page's text blocks and placeholders that
match an entry below are swapped for the Hindi. Text without an entry stays English, so nothing breaks while
the list grows. Guest invite pages (/e/, /i/) are skipped: they already speak the card's own language."""
import html
import re
from contextvars import ContextVar

COOKIE = "ui"
SKIP_PREFIXES = ("/admin", "/e/", "/i/", "/static", "/webhooks")
_current: ContextVar[str] = ContextVar("ui_lang", default="en")

HI = {
    # header & footer
    "Occasions": "अवसर", "Samples": "नमूने", "How it works": "कैसे काम करता है", "Pricing": "क़ीमत",
    "Done-for-you": "हम बनाएँ", "Create free": "मुफ़्त बनाएँ",
    "Beautiful invitations for weddings and every occasion, ready to share on WhatsApp":
        "शादी और हर मौक़े के लिए सुंदर निमंत्रण, WhatsApp पर भेजने के लिए तैयार",
    "Contact": "संपर्क", "Policies": "नीतियाँ", "Popular invitations": "लोकप्रिय निमंत्रण",
    "Invitation wording & messages": "निमंत्रण संदेश और शब्द", "Real invitations": "असली निमंत्रण",
    "Terms & photo consent": "नियम और फ़ोटो सहमति", "Privacy policy": "गोपनीयता नीति",
    "Refund & revision policy": "रिफ़ंड और बदलाव नीति", "© 2026 Invite All. Made with love in India.": "© 2026 Invite All. भारत में प्यार से बनाया गया।",
    "All 10 languages & occasions →": "सभी 10 भाषाएँ और अवसर →",
    # homepage hero
    "Not just a card.": "सिर्फ़ एक कार्ड नहीं,", "An invitation they'll never forget.": "ऐसा निमंत्रण जो सब याद रखें।",
    "Weddings, birthdays, pujas, anniversaries and every celebration: palace doors swing open, petals fall, your music plays, and each guest is greeted by name. Share on WhatsApp and know exactly who's coming.":
        "शादी, जन्मदिन, पूजा, वर्षगाँठ और हर उत्सव: महल के दरवाज़े खुलते हैं, फूल बरसते हैं, आपका संगीत बजता है और हर मेहमान का नाम लेकर स्वागत होता है। WhatsApp पर भेजिए और जानिए कौन आ रहा है।",
    "Occasion": "अवसर", "Demo language": "डेमो की भाषा", "✨ Open live demo": "✨ लाइव डेमो देखें",
    "🎨 Create yours free": "🎨 अपना मुफ़्त बनाएँ", "Free download · HD from ₹9": "मुफ़्त डाउनलोड · HD सिर्फ़ ₹9 से",
    "✦ Free to create": "✦ बनाना मुफ़्त", "✦ 28 occasions": "✦ 28 अवसर", "✦ 10 languages": "✦ 10 भाषाएँ", "✦ Pay by UPI": "✦ UPI से भुगतान",
    "💍 Wedding": "💍 शादी",
    # see your card in 1 second
    "See": "देखिए", "your": "अपना", "card in 1 second": "कार्ड 1 सेकंड में",
    "Type a name and watch the card change as you type. No sign-up, nothing to install.":
        "नाम लिखिए और कार्ड को बदलते देखिए। न साइन-अप, न कोई ऐप।",
    "Bride's name": "दुल्हन का नाम", "Groom's name": "दूल्हे का नाम", "Date": "तारीख़",
    "💖 Make it mine: create free →": "💖 यही चाहिए: मुफ़्त बनाएँ →",
    "Your names and date carry over. Add photos, functions, gifts and send it in about a minute.":
        "नाम और तारीख़ अपने-आप आगे भर जाएँगे। फ़ोटो, रस्में, शगुन जोड़िए और लगभग एक मिनट में भेजिए।",
    # features
    "An invitation that does the work for you": "निमंत्रण जो आपका काम आसान करे",
    "Families spend weeks calling relatives, chasing RSVPs and guessing headcounts for the caterer. We turn your invitation into a smart assistant.":
        "परिवार हफ़्तों रिश्तेदारों को फ़ोन करते हैं, जवाब का इंतज़ार करते हैं और खाने के लिए मेहमानों की गिनती का अंदाज़ा लगाते हैं। हम आपके निमंत्रण को एक स्मार्ट सहायक बना देते हैं।",
    "Cinematic opening": "शानदार शुरुआत",
    "Palace doors open to falling petals and your music. Guests feel the celebration before they arrive.":
        "महल के दरवाज़े खुलते हैं, फूल बरसते हैं और आपका संगीत बजता है। मेहमान आने से पहले ही उत्सव महसूस करते हैं।",
    "Personal for every guest": "हर मेहमान के लिए ख़ास", "Send on WhatsApp in one tap": "एक टैप में WhatsApp पर भेजें",
    "Know who's coming": "जानिए कौन आ रहा है", "Gifts, maps & reminders": "शगुन, नक्शा और रिमाइंडर",
    "Made by humans, in your language": "आपकी भाषा में, दिल से बनाया",
    "See what guests receive": "मेहमानों को क्या मिलता है, देखें", "See the family console": "परिवार का कंसोल देखें",
    "Not just weddings:": "सिर्फ़ शादी नहीं:", "every occasion": "हर अवसर",
    "Birthdays, anniversaries, pujas, baby ceremonies, festivals and business events, with the same live invite page, RSVP and WhatsApp-ready designs.":
        "जन्मदिन, वर्षगाँठ, पूजा, शिशु संस्कार, त्योहार और व्यापारिक कार्यक्रम: वही लाइव निमंत्रण पेज, RSVP और WhatsApp के लिए तैयार डिज़ाइन।",
    "Weddings": "शादी", "Birthdays": "जन्मदिन", "Anniversaries": "वर्षगाँठ", "Religious Pujas": "धार्मिक पूजा",
    "Baby & Family Ceremonies": "शिशु एवं पारिवारिक संस्कार", "Festivals & Parties": "त्योहार एवं पार्टियाँ",
    "Corporate & Business": "कॉर्पोरेट एवं व्यवसाय", "Browse all occasions": "सभी अवसर देखें",
    "In your language, from your tradition": "आपकी भाषा, आपकी परंपरा",
    "Each family's invite speaks their language, from the opening blessing to the RSVP button. Open a live demo:":
        "हर परिवार का निमंत्रण उनकी अपनी भाषा में: पहले आशीर्वाद से लेकर RSVP बटन तक। लाइव डेमो खोलें:",
    "Wedding styles": "शादी के डिज़ाइन",
    "Pick your occasion": "अपना अवसर चुनें", "See it instantly": "तुरंत देखें", "Download free or in HD": "मुफ़्त या HD में डाउनलोड करें",
    "Share & track RSVPs": "भेजें और जवाब देखें", "Create yours free": "अपना मुफ़्त बनाएँ",
    "Simple, honest pricing": "सीधी और साफ़ क़ीमत",
    "Create it yourself for any occasion. Pay only for the size you need.": "किसी भी अवसर का निमंत्रण ख़ुद बनाइए। सिर्फ़ उसी साइज़ के पैसे दीजिए जो चाहिए।",
    "Standard": "स्टैंडर्ड", "Free": "मुफ़्त", "Quick sharing, with a small credit": "जल्दी भेजने के लिए, छोटे क्रेडिट के साथ",
    "Perfect for WhatsApp & Instagram": "WhatsApp और Instagram के लिए बढ़िया", "Extra crisp on any phone or TV": "हर फ़ोन या टीवी पर एकदम साफ़",
    "Print-ready for cards & banners": "कार्ड और बैनर छपवाने के लिए तैयार",
    "Questions families ask": "परिवारों के सवाल", "Ask on WhatsApp": "WhatsApp पर पूछें",
    "Is it really free?": "क्या यह सच में मुफ़्त है?", "How do guests RSVP?": "मेहमान जवाब कैसे देते हैं?",
    "Can the card be in Hindi or my regional language?": "क्या कार्ड हिंदी या मेरी क्षेत्रीय भाषा में बन सकता है?",
    "Are my photos safe?": "क्या मेरी फ़ोटो सुरक्षित हैं?", "Which occasions can I make invitations for?": "किन अवसरों के लिए निमंत्रण बना सकते हैं?",
    "Made on Invite All": "Invite All पर बने", "this week": "इस हफ़्ते", "See all real invitations →": "सभी असली निमंत्रण देखें →",
    # create form
    "Create your wedding invitation": "अपनी शादी का निमंत्रण बनाएँ", "free": "मुफ़्त",
    "Fill in a few details and see your invitation in seconds. Download it free, or get HD from just":
        "कुछ जानकारी भरिए और सेकंडों में निमंत्रण देखिए। मुफ़्त डाउनलोड करें, या HD लें सिर्फ़",
    "✦ Free download": "✦ मुफ़्त डाउनलोड", "✦ Cards for every function": "✦ हर रस्म का कार्ड", "✦ Shareable invite page with RSVP": "✦ RSVP के साथ निमंत्रण पेज",
    "What are you celebrating?": "आप क्या मना रहे हैं?", "Selected:": "चुना गया:",
    "· the form below adapts to your choice ·": "· नीचे का फ़ॉर्म आपकी पसंद के हिसाब से बदलेगा ·", "samples & live demos ↗": "नमूने और लाइव डेमो ↗",
    "The couple": "वर-वधू", "Invitation language *": "निमंत्रण की भाषा *", "Invited by": "निमंत्रक", "optional": "वैकल्पिक",
    "in your script": "अपनी लिपि में", "recommended": "सुझाया गया", "+ Add parents' names": "+ माता-पिता के नाम जोड़ें", "(optional)": "(वैकल्पिक)",
    "Bride's parents": "दुल्हन के माता-पिता", "Groom's parents": "दूल्हे के माता-पिता",
    "Add photos": "फ़ोटो जोड़ें", "optional, but they make it special": "वैकल्पिक, पर इनसे निमंत्रण ख़ास बनता है",
    "Bride's photo": "दुल्हन की फ़ोटो", "Groom's photo": "दूल्हे की फ़ोटो", "Family photo": "परिवार की फ़ोटो", "Shown on the first page": "पहले पेज पर दिखेगी",
    "✨ Enhance my photos": "✨ मेरी फ़ोटो निखारें", "photo terms": "फ़ोटो के नियम",
    "Receive gifts & shagun": "शगुन और उपहार पाएँ",
    "Guests who can't come, or want to send their blessings, can pay you directly from the invitation with any UPI app. Add any one of these.":
        "जो मेहमान नहीं आ पा रहे या आशीर्वाद भेजना चाहते हैं, वे निमंत्रण से ही किसी भी UPI ऐप से सीधे आपको भेज सकते हैं। इनमें से कोई एक जोड़ें।",
    "UPI ID": "UPI ID", "or UPI mobile number": "या UPI मोबाइल नंबर", "Receiver's name": "पाने वाले का नाम",
    "or upload your payment QR code": "या अपना पेमेंट QR कोड अपलोड करें",
    "Wedding details": "शादी की जानकारी", "Wedding date": "शादी की तारीख़", "Time": "समय", "Hour": "घंटा", "Time format:": "समय का प्रारूप:",
    "12-hour (AM / PM)": "12 घंटे (AM / PM)", "24-hour": "24 घंटे", "Venue *": "स्थान *", "City": "शहर", "Address": "पता", "for the map": "नक्शे के लिए",
    "+ Add Haldi, Mehndi, Sangeet, Reception…": "+ हल्दी, मेहंदी, संगीत, रिसेप्शन जोड़ें…", "(each gets its own matching card)": "(हर रस्म का अपना कार्ड बनेगा)",
    "Pick a style": "डिज़ाइन चुनें", "Where should we send it?": "कहाँ भेजें?", "Your name": "आपका नाम", "Email": "ईमेल",
    "You can also add this later. By continuing you accept our": "यह बाद में भी जोड़ सकते हैं। आगे बढ़कर आप हमारी इन बातों से सहमत हैं:",
    "terms": "नियम", "and": "और", "Free to create": "बनाना मुफ़्त", "HD from ₹9": "HD ₹9 से",
    "✨ Create my invitation": "✨ मेरा निमंत्रण बनाएँ",
   
    # preview / order pages
    "Your cards": "आपके कार्ड", "Download your e-invite": "अपना ई-निमंत्रण डाउनलोड करें",
    "📨 Send a personal invitation": "📨 व्यक्तिगत निमंत्रण भेजें", "Guest's name *": "मेहमान का नाम *",
    "Create personal invite": "व्यक्तिगत निमंत्रण बनाएँ", "Copy": "कॉपी", "Preview": "झलक",
    "📸 Photos on your invitation": "📸 निमंत्रण पर फ़ोटो", "Save photos": "फ़ोटो सेव करें",
    # gallery & wording
    "Invitation Wording & Messages": "निमंत्रण संदेश और शब्द", "More invitation messages": "और निमंत्रण संदेश", "Put it on a card": "इसे कार्ड पर लगाएँ",
    "Make one like this": "ऐसा ही बनाएँ", "Be the first in the gallery ✨": "गैलरी में सबसे पहले आइए ✨", "All": "सभी",
    # create form steps
    'Names': 'नाम',
    'Family & blessings': 'परिवार और आशीर्वाद',
    'Functions': 'रस्में',
    'Guests & gifts': 'मेहमान और शगुन',
    'Design': 'डिज़ाइन',
    'Family & blessings optional': 'परिवार और आशीर्वाद वैकल्पिक',
    'Everything a traditional card says besides the names. It appears on your invite page and PDF.': 'नामों के अलावा जो कुछ पारंपरिक कार्ड पर लिखा जाता है। यह आपके निमंत्रण पेज और PDF पर दिखेगा।',
    'With the blessings of': 'आशीर्वाद',
    'Eagerly awaiting you': 'स्वागतोत्सुक',
    "The children's line": 'बाल मनुहार',
    'Dress code': 'ड्रेस कोड',
    'Your guest list': 'आपकी मेहमान सूची',
    'optional, saves hours': 'वैकल्पिक, घंटों की बचत',
    'No more writing names on every card. Paste your list once: after you create, each guest has their own card with their name on it, ready to send on WhatsApp in one tap.': 'अब हर कार्ड पर हाथ से नाम लिखने की ज़रूरत नहीं। सूची एक बार चिपकाइए: बनाने के बाद हर मेहमान का उसके नाम वाला कार्ड तैयार होगा, एक टैप में WhatsApp पर भेजने के लिए।',
    'One guest or family per line:': 'हर लाइन में एक मेहमान या परिवार:',
    'name, mobile (mobile optional)': 'नाम, मोबाइल (मोबाइल वैकल्पिक)',
    'Contact for guests': 'मेहमानों के लिए संपर्क',
    'Who should guests call for directions, stay or pickup? Shown with call and WhatsApp buttons.': 'रास्ते, ठहरने या स्टेशन से लाने के लिए मेहमान किसे फ़ोन करें? कॉल और WhatsApp बटन के साथ दिखेगा।',
    'Name 1': 'नाम 1',
    'Name 2': 'नाम 2',
    'Mobile 1': 'मोबाइल 1',
    'Mobile 2': 'मोबाइल 2',
    'Gifts & shagun': 'उपहार और शगुन',
    'No note': 'कोई नोट नहीं',
    '"Your blessings are our gift"': '"आपका आशीर्वाद ही हमारा उपहार है"',
    '"No boxed gifts please"': '"कृपया डिब्बाबंद उपहार न लाएँ"',
    'Your invitation will include': 'आपके निमंत्रण में होगा',
    '← Back': '← पीछे',
    'Next →': 'आगे →',
    'Step 1 of 5 · Names': 'चरण 1/5 · नाम',
    'Free to create · HD from ₹9': 'बनाना मुफ़्त · HD ₹9 से',
    'PH:Late Smt. & Shri Ram Prasad Sharma (Dada-Dadi)': 'स्व. श्रीमती एवं श्री रामप्रसाद शर्मा (दादा-दादी)',
    'PH:Chacha-Chachi, Mama-Mami, Bua-Phupha and all the Sharma family': 'चाचा-चाची, मामा-मामी, बुआ-फूफा एवं समस्त शर्मा परिवार',
    'PH:e.g. Traditional / pastel ethnic': 'जैसे: पारंपरिक / हल्के रंग',
    'PH:Dress code (e.g. yellow for Haldi)': 'ड्रेस कोड (जैसे: हल्दी में पीला)',
    'PH:Rakesh Sharma (Papa)': 'राकेश शर्मा (पापा)',
    'PH:Rohit (Bhaiya)': 'रोहित (भैया)',
    'Lord Ganesha & "Shri Ganeshaya Namah"': 'भगवान गणेश और "श्री गणेशाय नमः"',
    'on the card, cover and invite page.': 'कार्ड, कवर और निमंत्रण पेज पर।',
    'For Hindu weddings and pujas; not added to Nikah, church or Punjabi designs. Untick if your family prefers without.': 'हिंदू शादी और पूजा के लिए; निकाह, चर्च या पंजाबी डिज़ाइन पर नहीं जुड़ता। अगर आपका परिवार नहीं चाहता तो टिक हटा दें।',
    '+ Add parents, degree & home town': '+ माता-पिता, डिग्री और शहर जोड़ें',
    '(optional, printed under each name like a traditional card)': '(वैकल्पिक, पारंपरिक कार्ड की तरह हर नाम के नीचे छपेगा)',
    "👰 Bride's side": '👰 वधू पक्ष',
    "🤵 Groom's side": '🤵 वर पक्ष',
    'Degree / profession': 'डिग्री / व्यवसाय',
    "Father's name": 'पिता का नाम',
    "Mother's name": 'माता का नाम',
    'Home town / address': 'शहर / पता',
    'short': 'संक्षेप में',
    '📱 Your invitations on this phone': '📱 इस फ़ोन पर आपके निमंत्रण',
    'Forget on this phone': 'इस फ़ोन से हटाएँ',
    '✏️ Edit details': '✏️ जानकारी बदलें',
    'Fix a spelling, change the date or venue': 'वर्तनी ठीक करें, तारीख़ या स्थान बदलें',
    'Edit details': 'जानकारी बदलें',
    '← Back to your invitation': '← अपने निमंत्रण पर वापस',
    "Fix a spelling, change the date or venue, or add family details. Your card is redrawn in the same design, and links you've already sent keep working.": 'वर्तनी ठीक करें, तारीख़ या स्थान बदलें, या परिवार की जानकारी जोड़ें। आपका कार्ड उसी डिज़ाइन में दोबारा बनेगा, और भेजे गए लिंक चलते रहेंगे।',
    '💾 Save & redraw my card': '💾 सेव करें और कार्ड दोबारा बनाएँ',
    'Cancel': 'रद्द करें',
    '✓ Saved. Your card has been redrawn with the new details.': '✓ सेव हो गया। आपका कार्ड नई जानकारी के साथ दोबारा बन गया है।',
    '⏰ Reminder': '⏰ याद दिलाएँ',
    '🙏 Thank you': '🙏 धन्यवाद भेजें',
    'Or pay by card / netbanking on Razorpay': 'या Razorpay पर कार्ड / नेटबैंकिंग से भुगतान करें',
    # homepage feature cards
    'Send anywhere in one tap': 'एक टैप में कहीं भी भेजें',
    '"A special invitation for Sharma Family": each guest gets their own card, PDF and link with their name on it, free.': '"शर्मा परिवार के लिए विशेष निमंत्रण": हर मेहमान को उसके नाम वाला अपना कार्ड, PDF और लिंक, मुफ़्त।',
    'WhatsApp, SMS, Telegram, Instagram, Facebook or email, straight from your own phone, so it costs nothing.': 'WhatsApp, SMS, Telegram, Instagram, Facebook या ईमेल: सीधे अपने फ़ोन से, बिलकुल मुफ़्त।',
    'See live who opened, who replied, headcount per function, veg/Jain counts and who needs station pickup. Export it for your caterer.': 'लाइव देखिए किसने खोला, किसने जवाब दिया, हर रस्म में कितने लोग, शाकाहारी/जैन गिनती और किसे स्टेशन से लाना है। कैटरर के लिए डाउनलोड करें।',
    'Guests send shagun or gifts straight to your bank with any UPI app: add your UPI ID, mobile number or payment QR. Plus Google Maps for every venue, dress codes and add-to-calendar reminders.': 'मेहमान किसी भी UPI ऐप से शगुन सीधे आपके बैंक में भेजते हैं: अपना UPI ID, मोबाइल नंबर या QR जोड़ें। साथ में हर स्थान का Google Maps, ड्रेस कोड और कैलेंडर रिमाइंडर।',
    'Palace doors open to falling petals and your music. Guests feel the celebration before they arrive.': 'महल के दरवाज़े खुलते हैं, फूल बरसते हैं और आपका संगीत बजता है। मेहमान आने से पहले ही उत्सव महसूस करते हैं।',
    'In your language, spelled right': 'आपकी भाषा में, सही वर्तनी के साथ',
    'Hindi and 8 regional languages with every matra correct, names in your own script, and automatic quality checks on every card.': 'हिंदी और 8 क्षेत्रीय भाषाएँ, हर मात्रा सही, नाम आपकी अपनी लिपि में, और हर कार्ड की अपने-आप जाँच।',
    '"I\'m invited!" selfie frame': '"मुझे निमंत्रण मिला है!" सेल्फ़ी फ्रेम',
    'Guests take a selfie in a frame with your names and date and post it on their WhatsApp status or Instagram story.': 'मेहमान आपके नाम और तारीख़ वाले फ्रेम में सेल्फ़ी लेकर अपने WhatsApp स्टेटस या Instagram स्टोरी पर लगाते हैं।',
    'See it as you type': 'लिखते ही देखें',
    'Your card redraws live while you type the names and date, so you know exactly how it looks before you create it.': 'नाम और तारीख़ लिखते ही कार्ड बदलता है, ताकि बनाने से पहले ही पता चले कि वह कैसा दिखेगा।',
    '230 ready messages': '230 तैयार संदेश',
    'Lost for words? Copy beautiful invitation messages and shayari in Hindi and English for every occasion, in one tap.': 'शब्द नहीं सूझ रहे? हर अवसर के लिए हिंदी और अंग्रेज़ी में सुंदर निमंत्रण संदेश और शायरी, एक टैप में कॉपी करें।',
    'PDF, long image & 4K print': 'PDF, लंबी इमेज और 4K प्रिंट',
    'One PDF booklet, one long image for WhatsApp, and sizes up to 4K that any local press can print as cards or banners.': 'एक PDF पुस्तिका, WhatsApp के लिए एक लंबी इमेज, और 4K तक के साइज़ जिन्हें कोई भी प्रेस कार्ड या बैनर के रूप में छाप सके।',
    # create form, per occasion (translated in public._create_context)
    "Who's it for?": "किसके लिए?", "When & where": "कब और कहाँ", "Hosted by": "आयोजक", "Second photo": "दूसरी फ़ोटो",
    "Team / venue photo": "टीम / स्थान की फ़ोटो", "The Sharma family": "शर्मा परिवार", "The leadership team": "प्रबंधन टीम",
    "Baby's name": "शिशु का नाम", "Baby's name (or 'Baby of Priya & Rohan')": "शिशु का नाम (या 'प्रिया एवं रोहन का शिशु')",
    "Baby's photo": "शिशु की फ़ोटो", "Birthday person's photo": "जन्मदिन वाले की फ़ोटो", "Birthday star's photo": "बर्थडे स्टार की फ़ोटो",
    "Business / store name": "व्यवसाय / दुकान का नाम", "Child's name": "बच्चे का नाम", "Child's photo": "बच्चे की फ़ोटो",
    "Company logo": "कंपनी का लोगो", "Company name": "कंपनी का नाम", "Family name": "परिवार का नाम",
    "Father-to-be (optional)": "होने वाले पिता (वैकल्पिक)", "Father-to-be's photo": "होने वाले पिता की फ़ोटो",
    "Followed by (optional)": "इसके बाद (वैकल्पिक)", "Host family": "आयोजक परिवार", "Host family / committee": "आयोजक परिवार / समिति",
    "Host family photo": "आयोजक परिवार की फ़ोटो", "Host's photo": "आयोजक की फ़ोटो", "Hosted by / birthday person": "आयोजक / जन्मदिन वाले",
    "Inaugurated by (optional)": "उद्घाटनकर्ता (वैकल्पिक)", "Logo or storefront photo": "लोगो या दुकान की फ़ोटो",
    "Milestone age": "ख़ास उम्र", "Rituals (optional)": "अनुष्ठान (वैकल्पिक)", "Mother-to-be": "होने वाली माँ", "Mother-to-be's photo": "होने वाली माँ की फ़ोटो", "Name": "नाम",
    "Partner's name": "जीवनसाथी का नाम", "Partner's photo": "जीवनसाथी की फ़ोटो", "Photo": "फ़ोटो", "Product name": "उत्पाद का नाम",
    "Product or logo image": "उत्पाद या लोगो की तस्वीर", "Theme": "थीम", "Theme (optional)": "थीम (वैकल्पिक)",
    "Turning (age)": "उम्र (कितने साल)", "Years (25 = Silver, 50 = Golden)": "वर्ष (25 = रजत, 50 = स्वर्ण)", "Years together": "साथ के वर्ष",
    # placeholders
    "PH:e.g. Ananya": "जैसे: अनन्या", "PH:e.g. Arjun": "जैसे: अर्जुन", "PH:The Sharma & Mehta families": "शर्मा एवं मेहता परिवार",
    "PH:e.g. Jaipur": "जैसे: जयपुर", "PH:e.g. The Royal Palace Gardens": "जैसे: रॉयल पैलेस गार्डन्स", "PH:Ananya": "अनन्या", "PH:Arjun": "अर्जुन",
}

_TEXT = re.compile(r">([^<>]+)<")
_PLACEHOLDER = re.compile(r'placeholder="([^"]*)"')
_BLOCKS = re.compile(r"(<(script|style)\b[^>]*>.*?</\2>)", re.S | re.I)


def lang() -> str:
    return _current.get()


def set_lang(value: str) -> None:
    _current.set("hi" if value == "hi" else "en")


def tr(text: str) -> str:
    """One string in the visitor's language (for text built in Python, e.g. the create form's per-occasion labels)."""
    return HI.get(text, text) if lang() == "hi" else text


def _swap_text(m: re.Match) -> str:
    raw = m.group(1)
    key = " ".join(html.unescape(raw).split())
    hindi = HI.get(key)
    if not hindi:
        return m.group(0)
    lead, trail = raw[: len(raw) - len(raw.lstrip())], raw[len(raw.rstrip()):]
    return f">{lead}{html.escape(hindi, quote=False)}{trail}<"


def _swap_placeholder(m: re.Match) -> str:
    hindi = HI.get("PH:" + html.unescape(m.group(1)))
    return f'placeholder="{html.escape(hindi)}"' if hindi else m.group(0)


def translate_html(page: str) -> str:
    """Hindi text in a finished English page (scripts and styles left alone)."""
    parts = _BLOCKS.split(page)  # [text, <script…>…</script>, "script", text, …]
    out = []
    for i in range(0, len(parts), 3):
        out.append(_PLACEHOLDER.sub(_swap_placeholder, _TEXT.sub(_swap_text, parts[i])))
        if i + 1 < len(parts):
            out.append(parts[i + 1])
    return "".join(out).replace('<html lang="en">', '<html lang="hi">', 1)
