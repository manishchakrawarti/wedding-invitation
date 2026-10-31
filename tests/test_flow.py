import io
import hashlib
import hmac
import json
import re
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Asset, Guest, Invitee, Notification, Order, OrderStatus
from app.services import orders, payments
from app.services.overlay import RAQM
from app.utils import inr, normalize_phone

WEDDING = (date.today() + timedelta(days=60)).isoformat()


def order_form(**overrides):
    data = {
        "package": "basic", "style": "north_indian", "language": "en",
        "bride_name": "Ananya", "groom_name": "Arjun", "bride_family": "Mrs & Mr Sharma",
        "wedding_date": WEDDING, "venue_name": "The Leela Palace", "city": "Jaipur",
        "fn_wedding": "on", "fn_wedding_time": "19:30",
        "customer_name": "Ravi Sharma", "phone": "98765 43210", "email": "ravi@example.com",
        "payment_option": "full", "accept_terms": "on",
    }
    data.update(overrides)
    return data


def place_order(client, files=None, **overrides) -> Order:
    resp = client.post("/order", data=order_form(**overrides), files=files, follow_redirects=False)
    assert resp.status_code == 303, resp.text[:2000]
    token = resp.headers["location"].split("/")[2]
    return get(token)


def get(token: str) -> Order:
    with SessionLocal() as db:
        order = db.scalar(select(Order).where(Order.token == token))
        order.assets, order.payments, order.revisions, order.guests, order.events  # load relationships
        return order


def pay(client, order: Order, purpose: str = "") -> Order:
    page = client.get(f"/o/{order.token}/pay" + (f"?purpose={purpose}" if purpose else ""))
    assert page.status_code == 200
    payment_id = re.search(r"/pay/simulate/(\d+)", page.text).group(1)
    resp = client.post(f"/o/{order.token}/pay/simulate/{payment_id}", follow_redirects=False)
    assert resp.status_code == 303
    return get(order.token)


# --- units -------------------------------------------------------------------

def test_inr_lakh_grouping():
    assert inr(49900) == "₹499"
    assert inr(149999900) == "₹14,99,999"
    assert inr(1234567800) == "₹1,23,45,678"


def test_phone_normalization():
    assert normalize_phone("98765 43210") == "919876543210"
    assert normalize_phone("+91-98765-43210") == "919876543210"
    assert normalize_phone("098765 43210") == "919876543210"


def test_pricing_ignores_included_addons_and_applies_referral():
    assert orders.price("basic", ["rsvp", "express"], False) == (49900 + 99900 + 29900, 0, 179700)
    # Premium already includes RSVP/express/function cards.
    assert orders.price("premium", ["rsvp", "express", "function_cards"], True) == (299900, 10000, 289900)
    assert orders.effective_addons("basic", ["extra_revision", "bogus", "rsvp"]) == ["rsvp"]


def test_razorpay_signatures(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "razorpay_key_secret", "secret123")
    sig = hmac.new(b"secret123", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert payments.verify_checkout_signature("order_1", "pay_1", sig)
    assert not payments.verify_checkout_signature("order_1", "pay_2", sig)
    body = b'{"event":"x"}'
    assert payments.verify_webhook_signature(body, hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest())
    assert not payments.verify_webhook_signature(body, "nope")


# --- pages -------------------------------------------------------------------

def test_public_pages(client):
    for path in ["/", "/order", "/terms", "/privacy", "/refund", "/healthz"]:
        assert client.get(path).status_code == 200, path
    resp = client.get("/samples/north_indian.jpg")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"


def test_order_validation_errors(client):
    resp = client.post("/order", data=order_form(bride_name="", phone="123", accept_terms=""))
    assert resp.status_code == 422
    assert "Bride&#39;s name is required" in resp.text and "valid WhatsApp number" in resp.text
    resp = client.post("/order", data=order_form(language="hi"))
    assert resp.status_code == 422 and "script too" in resp.text


def test_photos_require_consent(client, photo_bytes):
    resp = client.post("/order", data=order_form(), files=[("photos", ("me.jpg", photo_bytes, "image/jpeg"))])
    assert resp.status_code == 422 and "photo consent" in resp.text


def test_admin_requires_auth(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401


# --- end-to-end flows ------------------------------------------------------------

def test_full_payment_flow_with_revision(client, admin_auth, photo_bytes):
    order = place_order(client, files=[("photos", ("me.jpg", photo_bytes, "image/jpeg"))], photo_consent="on")
    assert order.status == OrderStatus.PENDING_PAYMENT.value
    assert order.total == 49900 and len([a for a in order.assets if a.kind == "photo"]) == 1

    # Final files are locked before delivery.
    order = pay(client, order)
    assert order.status == OrderStatus.QC_REVIEW.value, [e.message for e in get(order.token).events]
    assert order.amount_paid == 49900 and order.current_version == 1
    final = next(a for a in order.assets if a.kind == "final")
    assert final.qc["passed"], final.qc
    assert client.get(f"/o/{order.token}/files/{final.id}").status_code == 403
    proof = next(a for a in order.assets if a.kind == "proof")
    assert client.get(f"/o/{order.token}/files/{proof.id}").status_code == 404  # not reviewed by owner yet

    # Owner reviews and sends proof.
    assert client.get(f"/admin/orders/{order.id}", auth=admin_auth).status_code == 200
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    assert get(order.token).status == OrderStatus.PROOF_SENT.value
    assert client.get(f"/o/{order.token}/proof").status_code == 200
    assert client.get(f"/o/{order.token}/files/{proof.id}").status_code == 200

    # Customer asks for changes; owner regenerates and re-sends.
    client.post(f"/o/{order.token}/proof/changes", data={"notes": "More marigolds please"})
    order = get(order.token)
    assert order.status == OrderStatus.CHANGES_REQUESTED.value and order.revisions_used == 1
    client.post(f"/admin/orders/{order.id}/regenerate", data={"notes": "More marigolds"}, auth=admin_auth)
    order = get(order.token)
    assert order.status == OrderStatus.QC_REVIEW.value and order.current_version == 2
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)

    # Approve → fully paid → delivered.
    client.post(f"/o/{order.token}/proof/approve")
    order = get(order.token)
    assert order.status == OrderStatus.DELIVERED.value
    final = next(a for a in order.assets if a.kind == "final" and a.version == 2)
    resp = client.get(f"/o/{order.token}/files/{final.id}?download=1")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"
    assert "attachment" in resp.headers["content-disposition"]

    with SessionLocal() as db:
        kinds = [n.body for n in db.scalars(select(Notification).where(Notification.order_id == order.id))]
    assert any("proof for Ananya & Arjun is ready" in b for b in kinds) and any("final invitation" in b for b in kinds)


def test_advance_then_balance(client, admin_auth):
    order = place_order(client, payment_option="advance", package="video")
    order = pay(client, order)
    assert order.amount_paid == 75000 and order.balance_due == 74900
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    client.post(f"/o/{order.token}/proof/approve")
    order = get(order.token)
    assert order.status == OrderStatus.BALANCE_DUE.value
    order = pay(client, order, "balance")
    assert order.status == OrderStatus.DELIVERED.value and order.balance_due == 0


def test_revision_limit_then_paid_revision(client, admin_auth):
    order = place_order(client)
    pay(client, order)
    for _ in range(2):
        client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
        client.post(f"/o/{order.token}/proof/changes", data={"notes": "change"})
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    resp = client.post(f"/o/{order.token}/proof/changes", data={"notes": "third"}, follow_redirects=False)
    assert resp.headers["location"].endswith("/pay?purpose=revision")
    order = pay(client, get(order.token), "revision")
    assert order.extra_revisions == 1 and order.revisions_left == 1 and order.amount_paid == 49900 + 19900


def test_premium_function_cards_and_rsvp(client, admin_auth):
    order = place_order(
        client, package="premium",
        fn_haldi="on", fn_haldi_date=WEDDING, fn_haldi_time="10:00",
        fn_mehndi="on", fn_mehndi_venue="Sharma Residence",
    )
    order = pay(client, order)
    finals = [a for a in order.assets if a.kind == "final"]
    assert sorted(a.card_key for a in finals) == ["haldi", "main", "mehndi"]
    assert order.rsvp_slug == "ananya-weds-arjun" or order.rsvp_slug.startswith("ananya-weds-arjun")

    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    client.post(f"/o/{order.token}/proof/approve")
    slug = order.rsvp_slug
    page = client.get(f"/e/{slug}")
    assert page.status_code == 200 and "Haldi" in page.text
    assert order.token not in page.text  # never leak the private order link to guests
    assert client.get(f"/e/{slug}/invite").status_code == 200
    assert client.get(f"/e/{slug}/qr.png").status_code == 200

    client.post(f"/e/{slug}/rsvp", data={"name": "Meena Aunty", "attending": "yes", "headcount": "3", "functions": ["haldi"]})
    with SessionLocal() as db:
        guest = db.scalar(select(Guest).where(Guest.order_id == order.id))
    assert guest.name == "Meena Aunty" and guest.headcount == 3
    assert client.get(f"/e/{slug}/guests").status_code == 403
    guests = client.get(f"/e/{slug}/guests?key={order.token}")
    assert guests.status_code == 200 and "Meena Aunty" in guests.text


def test_referral_discount(client):
    first = place_order(client)
    second = place_order(client, referral=first.referral_code.lower())
    assert second.discount == 10000 and second.total == 39900 and second.referred_by_code == first.referral_code


def test_failed_generation_alerts_and_retries(client, monkeypatch):
    from app.services import pipeline

    calls = []

    class Boom:
        def generate(self, *a, **k):
            calls.append(1)
            raise RuntimeError("model overloaded")

    monkeypatch.setattr(pipeline, "get_generator", lambda: Boom())
    order = pay(client, place_order(client))
    assert order.status == OrderStatus.FAILED.value
    assert len(calls) == 3  # generation_max_attempts


def test_hindi_card_blocked_without_shaping(client):
    order = pay(client, place_order(client, language="hi", bride_name_local="अनन्या", groom_name_local="अर्जुन"))
    final = next(a for a in order.assets if a.kind == "final")
    shaping = next(c for c in final.qc["checks"] if c["name"] == "script_shaping")
    assert shaping["status"] == ("pass" if RAQM else "fail")


def test_razorpay_webhook_marks_paid(client):
    order = place_order(client)
    client.get(f"/o/{order.token}/pay")
    payment = get(order.token).payments[0]
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_X", "order_id": payment.provider_order_id}}}}).encode()
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig}).status_code == 200
    assert get(order.token).amount_paid == 49900
    # Replays are idempotent.
    client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert get(order.token).amount_paid == 49900


def test_whatsapp_auto_reply(client):
    order = place_order(client)
    msg = {"entry": [{"changes": [{"value": {"messages": [{"from": "919000000001", "type": "text", "text": {"body": f"status {order.public_id}"}}]}}]}]}
    client.post("/webhooks/whatsapp", json=msg)
    with SessionLocal() as db:
        reply = db.scalars(select(Notification).where(Notification.recipient == "919000000001")).all()[-1]
    assert order.public_id in reply.body and "Awaiting payment" in reply.body


def test_retention_cleanup(client, photo_bytes):
    from app.models import utcnow
    from app.services.maintenance import cleanup_expired

    order = place_order(client, files=[("photos", ("me.jpg", photo_bytes, "image/jpeg"))], photo_consent="on")
    with SessionLocal() as db:
        photo = db.scalar(select(Asset).where(Asset.order_id == order.id, Asset.kind == "photo"))
        photo.created_at = utcnow() - timedelta(days=31)
        db.commit()
        result = cleanup_expired(db)
        db.refresh(photo)
    assert result["photos"] >= 1 and photo.deleted_at is not None


def test_razorpay_me_manual_payment(client, admin_auth, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "razorpay_me_url", "https://razorpay.me/@example")
    order = place_order(client)
    page = client.get(f"/o/{order.token}/pay")
    assert "https://razorpay.me/@example" in page.text and "Simulate payment" not in page.text
    payment_id = re.search(r"/pay/claim/(\d+)", page.text).group(1)
    assert client.post(f"/o/{order.token}/pay/simulate/{payment_id}").status_code == 404

    client.post(f"/o/{order.token}/pay/claim/{payment_id}", data={"reference": "pay_ABC123"})
    order = get(order.token)
    assert order.status == OrderStatus.PENDING_PAYMENT.value and order.payments[0].status == "claimed"
    assert "pay_ABC123" in client.get(f"/o/{order.token}/pay").text
    assert "payment(s) to confirm" in client.get("/admin", auth=admin_auth).text

    client.post(f"/admin/payments/{payment_id}/confirm", auth=admin_auth)
    order = get(order.token)
    assert order.amount_paid == 49900 and order.status == OrderStatus.QC_REVIEW.value


def test_one_rupee_test_order(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "test_order_code", "secret-code")
    assert "TEST ORDER" not in client.get("/order?test=wrong").text
    assert "TEST ORDER" in client.get("/order?test=secret-code").text

    order = place_order(client, package="premium", test="secret-code", payment_option="advance")
    assert order.total == 100 and order.payment_option == "full" and order.source == "test"
    normal = place_order(client, package="premium", test="wrong")
    assert normal.total == 299900 and normal.source == "website"


def test_resend_and_test_email(client, admin_auth):
    order = place_order(client)
    resp = client.post(f"/admin/orders/{order.id}/resend", auth=admin_auth)
    assert "order_received" in resp.text
    resp = client.post("/admin/notifications/test-email", data={"to": "me@example.com"}, auth=admin_auth)
    assert "SMTP is not configured" in resp.text


def test_smart_guest_invites(client, admin_auth):
    order = place_order(client, package="premium", fn_haldi="on", fn_haldi_date=WEDDING, fn_reception="on")
    order = pay(client, order)
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    client.post(f"/o/{order.token}/proof/approve")
    slug, key = order.rsvp_slug, order.token
    assert "family console" in client.get(f"/o/{order.token}").text.lower()

    # Bulk add: functions, phone and side are parsed per line; empty functions -> defaults.
    resp = client.post(f"/e/{slug}/guests/add", data={
        "key": key, "guests": "Sharma Family, 98765 43210, haldi wedding, bride\nMeena Aunty, reception\nRahul",
        "default_functions": ["wedding"],
    })
    assert "Added 3 guest(s)" in resp.text
    assert "wa.me/919876543210?text=" in resp.text  # one-tap WhatsApp send with a personal message
    assert client.post(f"/e/{slug}/guests/add", data={"key": "wrong", "guests": "X"}).status_code == 403
    sharma, meena, rahul = _invitees(order.id)
    assert sharma.functions == ["haldi", "wedding"] and sharma.phone == "919876543210" and sharma.side == "bride"
    assert meena.functions == ["reception"] and rahul.functions == ["wedding"]

    # Personal page: greets by name, shows only invited functions, counts opens (not previews).
    page = client.get(f"/i/{meena.code}")
    assert "Dear Meena Aunty" in page.text and "Reception" in page.text and "Haldi" not in page.text
    client.get(f"/i/{meena.code}?preview=1")
    assert _invitees(order.id)[1].open_count == 1

    client.post(f"/i/{sharma.code}/rsvp", data={
        "attending": "yes", "headcount": "4", "functions": ["haldi", "wedding", "reception"], "food": "jain",
        "arrival_date": WEDDING, "arrival_mode": "train", "needs_pickup": "on", "message": "Badhaai ho!",
    })
    sharma = _invitees(order.id)[0]
    assert sharma.attending_functions == ["haldi", "wedding"]  # can't RSVP to functions they're not invited to
    assert sharma.needs_pickup and sharma.food == "jain"

    console = client.get(f"/e/{slug}/guests?key={key}")
    assert console.status_code == 200 and "Need pickup" in console.text
    assert "Badhaai ho!" in client.get(f"/e/{slug}").text  # blessings wall
    ics = client.get(f"/e/{slug}/calendar/haldi.ics")
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text
    csv = client.get(f"/e/{slug}/guests.csv?key={key}").text
    assert "Sharma Family" in csv and "/i/" in csv

    client.post(f"/e/{slug}/details", data={"key": key, "hosts": "The Kapoor family", "upi_id": "me@upi", "dress_haldi": "Yellow"})
    page = client.get(f"/i/{rahul.code}").text
    assert "The Kapoor family" in page and "upi://pay?pa=me%40upi" in page.replace("&amp;", "&")
    assert client.get(f"/e/{slug}/shagun.png").status_code == 200


def _invitees(order_id):
    from app.models import Invitee
    with SessionLocal() as db:
        return db.scalars(select(Invitee).where(Invitee.order_id == order_id).order_by(Invitee.id)).all()


def test_live_demo(client):
    from app.services import demo

    demo.ensure_demo()
    demo.ensure_demo()  # idempotent
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"].startswith("/i/")
    page = client.get(resp.headers["location"])
    assert "Sharma Family" in page.text and "Our Story" in page.text
    assert client.get("/demo/console").status_code == 200
    with SessionLocal() as db:
        weddings = db.scalars(select(Order).where(Order.source == "demo", Order.event_type == "wedding")).all()
        assert len(weddings) == len(demo.DEMOS)

    # Every language demo renders fully in its own language and script.
    from app import i18n
    from app.services.overlay import RAQM

    for lang, cfg in demo.DEMOS.items():
        page = client.get(f"/demo/{lang}")
        assert page.status_code == 200, lang
        t = i18n.texts(lang)
        assert f'<html lang="{lang}">' in page.text, lang
        assert t["dear"].format(name=cfg["guest"]) in page.text, lang
        assert t["rsvp_title"] in page.text and t["tap"] in page.text, lang
        if cfg["bride"][1]:
            assert cfg["bride"][1] in page.text, lang
        if cfg["style"] != "christian":
            assert i18n.INVOCATIONS[lang] in page.text, lang
        assert client.get(f"/demo/{lang}/console").status_code == 200, lang
        # A card with broken Indian-script shaping is never shown to guests.
        has_card = f"/e/" in page.text and "/invite\"" in page.text
        assert has_card == (lang == "en" or RAQM), lang
    assert client.get("/demo/xx").status_code == 404


def test_translations_complete():
    from app import i18n
    from app.catalog import FUNCTIONS, LANGUAGES

    for lang in LANGUAGES:
        if lang == "en":
            continue
        assert set(i18n.T[lang]) == set(i18n.EN), lang
        assert set(i18n.FUNCTION_NAMES[lang]) == set(FUNCTIONS), lang
        assert lang in i18n.INVOCATIONS and lang in i18n.WEB_FONTS, lang
        for key in ("dear", "invite_para"):  # placeholders must survive translation
            text = i18n.T[lang][key].format(name="X", hosts="H", bride="B", groom="G")
            assert "{" not in text, (lang, key)


def test_whatsapp_message_in_card_language():
    from types import SimpleNamespace as NS

    from app.services import invites

    order = NS(language="ta", bride_name="Meenakshi", groom_name="Karthik", bride_name_local="மீனாட்சி",
               groom_name_local="கார்த்திக்", wedding_date=date(2026, 12, 12), event=None)
    text = invites.whatsapp_text(order, NS(name="ஐயர் குடும்பம்", code="abc"))
    assert "அன்புள்ள ஐயர் குடும்பம்" in text and "மீனாட்சி" in text and "/i/abc" in text


def test_homepage_demo_language_picker(client):
    from app.services import demo

    demo.ensure_demo()
    home = client.get("/").text
    assert home.count('class="lang-select"') == 2 and 'formaction="/demo/console"' in home
    for code in ("en", "hi", "ta", "ml"):
        assert f'<option value="{code}"' in home
    # The picker submits ?lang=..., which must open that language's demo and console.
    page = client.get("/demo?lang=ta")
    assert '<html lang="ta">' in page.text
    console = client.get("/demo/console?lang=bn")
    assert console.status_code == 200 and "Rimjhim" in console.text  # Bengali demo couple


def create_instant(client, **overrides) -> Order:
    data = {"bride_name": "Priya", "groom_name": "Rohan", "language": "en", "style": "north_indian",
            "wedding_date": WEDDING, "wedding_time": "19:30", "venue_name": "ITC Rajputana", "city": "Jaipur"}
    data.update(overrides)
    resp = client.post("/create", data=data, follow_redirects=False)
    assert resp.status_code == 303, resp.text[:1500]
    assert resp.headers["location"].endswith("/preview")
    return get(resp.headers["location"].split("/")[2])


def _image_size(resp):
    from PIL import Image

    return Image.open(io.BytesIO(resp.content)).size


def test_instant_free_download_then_paid_sizes(client):
    assert client.get("/create").status_code == 200
    order = create_instant(client, fn_haldi="on", fn_haldi_date=WEDDING, hosts="The Kapoor family")
    assert order.status == OrderStatus.PREVIEW.value and order.total == 900 and order.amount_paid == 0
    assert sorted(a.card_key for a in order.assets if a.kind == "final") == ["haldi", "main"]
    wedding = next(f for f in order.functions if f["key"] == "wedding")
    assert wedding["time"] == "19:30"  # the quick "time" field lands on the ceremony
    final = next(a for a in order.assets if a.kind == "final" and a.card_key == "main")
    dl = f"/o/{order.token}/download/{final.id}"

    # Preview: Standard image is free; paid sizes and the HD final are locked.
    page = client.get(f"/o/{order.token}/preview").text
    assert "Get Full HD" in page and "Get 4K" in page and "⬇ Free" in page
    free = client.get(f"{dl}/free")
    assert free.status_code == 200 and _image_size(free) == (720, 900)
    assert client.get(f"{dl}/1080").status_code == 403
    assert client.get(f"/o/{order.token}/files/{final.id}").status_code == 403
    assert client.get(f"/o/{order.token}", follow_redirects=False).headers["location"].endswith("/preview")
    event = client.get(f"/e/{order.rsvp_slug}").text
    assert "Free preview" in event and 'disabled title="Available after unlocking"' in event
    assert client.get(f"/e/{order.rsvp_slug}/guests?key={order.token}").status_code == 403

    # Buy 2K (₹49): delivered; 2K and below unlocked, 4K still locked.
    resp = client.post(f"/o/{order.token}/unlock", data={"res": "2k"}, follow_redirects=False)
    assert resp.headers["location"].endswith("/pay?purpose=full")
    assert get(order.token).total == 4900
    order = pay(client, get(order.token))
    assert order.status == OrderStatus.DELIVERED.value and order.amount_paid == 4900
    two_k = client.get(f"{dl}/2k")
    assert two_k.status_code == 200 and _image_size(two_k) == (2048, 2560)
    assert _image_size(client.get(f"{dl}/1080")) == (1080, 1350)
    assert client.get(f"{dl}/4k").status_code == 403
    assert "+₹50" in client.get(f"/o/{order.token}").text  # upgrade offer shows only the difference

    # Upgrade to 4K: pay only the ₹50 difference.
    resp = client.post(f"/o/{order.token}/unlock", data={"res": "4k"}, follow_redirects=False)
    assert resp.headers["location"].endswith("/pay?purpose=balance")
    order = pay(client, get(order.token), "balance")
    assert order.amount_paid == 9900 and order.status == OrderStatus.DELIVERED.value
    four_k = client.get(f"{dl}/4k")
    assert four_k.status_code == 200 and _image_size(four_k) == (3840, 4800)
    assert four_k.headers["content-type"] == "image/jpeg"

    # Send to email after unlocking.
    status = client.get(f"/o/{order.token}").text
    assert "Send to email" in status and "Your invite page" in status
    resp = client.post(f"/o/{order.token}/email", data={"email": "priya@example.com"}, follow_redirects=False)
    assert resp.headers["location"].endswith("?emailed=logged#email")  # SMTP not configured in tests
    with SessionLocal() as db:
        note = db.scalars(select(Notification).where(Notification.recipient == "priya@example.com")).first()
    assert "2 card(s) are attached" in note.body and f"/e/{order.rsvp_slug}" in note.body


def test_instant_validation_rate_limit_and_hidden_package(client, monkeypatch):
    from app.config import settings

    resp = client.post("/create", data={"bride_name": "", "groom_name": "R", "language": "en", "style": "north_indian",
                                        "wedding_date": WEDDING, "venue_name": ""})
    assert resp.status_code == 422 and "Bride&#39;s name is required" in resp.text
    monkeypatch.setattr(settings, "instant_previews_per_hour", 0)
    resp = client.post("/create", data={"bride_name": "A", "groom_name": "B", "language": "en", "style": "north_indian",
                                        "wedding_date": WEDDING, "venue_name": "V"})
    assert resp.status_code == 422 and "several previews this hour" in resp.text
    # The ₹99 package can't be bought through the done-for-you order form.
    resp = client.post("/order", data=order_form(package="instant"))
    assert resp.status_code == 422


def test_test_coupon_unlocks_instant_preview(client, monkeypatch):
    from app.config import settings

    order = create_instant(client)
    # Disabled by default: no code configured.
    resp = client.post(f"/o/{order.token}/coupon", data={"code": "anything"}, follow_redirects=False)
    assert resp.headers["location"].endswith("/preview?coupon=invalid#unlock")

    monkeypatch.setattr(settings, "test_coupon_code", "TEST99-SECRET")
    client.post(f"/o/{order.token}/coupon", data={"code": "wrong"})
    assert get(order.token).status == OrderStatus.PREVIEW.value
    resp = client.post(f"/o/{order.token}/coupon", data={"code": "test99-secret"}, follow_redirects=False)
    assert resp.headers["location"].endswith("?coupon=1")
    order = get(order.token)
    assert order.status == OrderStatus.DELIVERED.value and order.total == 0 and order.discount == 9900
    final = next(a for a in order.assets if a.kind == "final")
    assert client.get(f"/o/{order.token}/files/{final.id}").status_code == 200
    # Only for ₹99 previews: it does nothing on a regular order.
    regular = place_order(client)
    client.post(f"/o/{regular.token}/coupon", data={"code": "TEST99-SECRET"})
    assert get(regular.token).status == OrderStatus.PENDING_PAYMENT.value


def test_einvite_pdf_and_long_image_in_sizes(client):
    import re

    import pytest

    from app.services import export

    if not export.chrome_binary():
        pytest.skip("Chrome/Chromium not installed")
    order = create_instant(client, fn_haldi="on", fn_haldi_date=WEDDING)
    base = f"/o/{order.token}/einvite"

    # Free preview: the live invitation is shown, and the 720p e-invite is free.
    page = client.get(f"/o/{order.token}/preview").text
    assert f'<iframe src="/e/{order.rsvp_slug}"' in page and "Download your e-invite" in page
    free_pdf = client.get(f"{base}/pdf/free")
    assert free_pdf.status_code == 200 and free_pdf.content.startswith(b"%PDF")
    # cover + main card + haldi card + celebrations + venue
    assert len(re.findall(rb"/Type\s*/Page[^s]", free_pdf.content)) == 5
    free_img = client.get(f"{base}/image/free")
    assert free_img.headers["content-type"] == "image/jpeg" and _image_size(free_img) == (720, 900 * 5)
    assert client.get(f"{base}/pdf/1080").status_code == 403

    # Buy Full HD (₹9): 1080 unlocked, 2K still locked.
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    assert order.amount_paid == 900 and order.status == OrderStatus.DELIVERED.value
    status = client.get(f"/o/{order.token}").text
    assert "Your complete e-invite" in status and f"{base}/pdf/1080" in status and f"{base}/pdf/2k" not in status
    assert client.get(f"{base}/pdf/1080").content.startswith(b"%PDF")
    assert _image_size(client.get(f"{base}/image/1080")) == (1080, 1350 * 5)
    assert client.get(f"{base}/image/2k").status_code == 403
    assert client.get(f"{base}/gif/1080").status_code == 404

    # The email carries the Full HD PDF.
    client.post(f"/o/{order.token}/email", data={"email": "e@example.com"})
    with SessionLocal() as db:
        note = db.scalars(select(Notification).where(Notification.recipient == "e@example.com")).first()
    assert "complete e-invite (PDF)" in note.body


def _photo(color):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 1000), color).save(buf, "JPEG")
    return buf.getvalue()


def test_bride_groom_and_family_photos(client):
    from app.models import utcnow
    from app.services import export
    from app.services.maintenance import cleanup_expired

    files = [("bride_photo", ("b.jpg", _photo((220, 120, 140)), "image/jpeg")),
             ("groom_photo", ("g.jpg", _photo((90, 120, 200)), "image/jpeg")),
             ("family_photo", ("f.jpg", _photo((120, 180, 90)), "image/jpeg"))]
    data = {"bride_name": "Priya", "groom_name": "Rohan", "language": "en", "style": "north_indian",
            "wedding_date": WEDDING, "venue_name": "ITC Rajputana", "hosts": "The Kapoor family"}

    # Photos need consent.
    resp = client.post("/create", data=data, files=files)
    assert resp.status_code == 422 and "permission to use these photos" in resp.text

    resp = client.post("/create", data={**data, "photo_consent": "on"}, files=files, follow_redirects=False)
    order = get(resp.headers["location"].split("/")[2])
    assert sorted(a.card_key for a in order.assets if a.kind == "portrait") == ["bride", "family", "groom"]

    # Live invite: photos by the names, family photo with "Invited by".
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert f"/e/{order.rsvp_slug}/portrait/bride" in page and f"/e/{order.rsvp_slug}/portrait/groom" in page
    assert f"/e/{order.rsvp_slug}/portrait/family" in page and "Invited by: <strong>The Kapoor family</strong>" in page
    photo = client.get(f"/e/{order.rsvp_slug}/portrait/bride")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert client.get(f"/e/{order.rsvp_slug}/portrait/nobody").status_code == 404

    # E-invite cover and note page carry the photos.
    with SessionLocal() as db:
        html, _ = export.build_html(db.get(Order, order.id), "free")
    assert html.count('class="portrait"') == 2 and 'class="family"' in html

    # Family console can replace a photo; unpaid previews' photos expire with the others.
    with SessionLocal() as db:
        o = db.get(Order, order.id)
        o.package = "premium"  # console is a Premium feature
        db.commit()
    client.post(f"/e/{order.rsvp_slug}/details", data={"key": order.token, "photo_consent": "on"},
                files=[("groom_photo", ("g2.jpg", _photo((10, 10, 10)), "image/jpeg"))])
    groom = [a for a in get(order.token).assets if a.kind == "portrait" and a.card_key == "groom"]
    assert len(groom) == 2 and sum(a.deleted_at is None for a in groom) == 1
    with SessionLocal() as db:
        for a in db.scalars(select(Asset).where(Asset.order_id == order.id, Asset.kind == "portrait")):
            a.created_at = utcnow() - timedelta(days=31)
        db.commit()
        cleanup_expired(db)
    assert all(a.deleted_at for a in get(order.token).assets if a.kind == "portrait")


def _create_with_photos(client, **extra):
    files = [("bride_photo", ("b.jpg", _photo((200, 150, 120)), "image/jpeg")),
             ("family_photo", ("f.jpg", _photo((120, 160, 100)), "image/jpeg"))]
    data = {"bride_name": "Asha", "groom_name": "Vivek", "language": "en", "style": "north_indian",
            "wedding_date": WEDDING, "venue_name": "Taj", "photo_consent": "on", **extra}
    resp = client.post("/create", data=data, files=files, follow_redirects=False)
    assert resp.status_code == 303, resp.text[:800]
    return get(resp.headers["location"].split("/")[2])


def test_photos_enhanced_by_default_original_kept(client):
    from PIL import Image

    from app.services.storage import storage

    order = _create_with_photos(client)
    shown = {a.card_key: a for a in order.assets if a.kind == "portrait" and not a.deleted_at}
    raws = {a.card_key: a for a in order.assets if a.kind == "portrait_raw"}
    assert set(shown) == set(raws) == {"bride", "family"}
    assert shown["bride"].meta["enhanced"] is True and shown["bride"].meta["ai"] is False
    bride = Image.open(io.BytesIO(storage.read(shown["bride"].path)))
    family = Image.open(io.BytesIO(storage.read(shown["family"].path)))
    assert abs(bride.width - bride.height) <= 2  # square, ready for the circle
    assert abs(family.width / family.height - 4 / 3) < 0.02  # 4:3 family frame

    # Opting out keeps the photo as uploaded (cleaned of EXIF only).
    plain = _create_with_photos(client, enhance_photos="off")
    meta = next(a.meta for a in plain.assets if a.kind == "portrait" and a.card_key == "bride")
    assert meta["enhanced"] is False


def test_ai_photo_retouch_used_and_costed_but_rejected_if_face_lost(client, monkeypatch):
    from PIL import Image

    from app.config import settings
    from app.models import CostEntry
    from app.services import photo_enhance, pipeline
    from app.services.generation import offline_generator

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(pipeline, "get_generator", lambda: offline_generator())  # cards stay offline
    monkeypatch.setattr(photo_enhance, "ai_retouch", lambda img: Image.new("RGB", img.size, (250, 230, 200)))
    order = _create_with_photos(client)
    shown = {a.card_key: a for a in get(order.token).assets if a.kind == "portrait" and not a.deleted_at}
    assert shown["bride"].meta["ai"] is True and shown["family"].meta["ai"] is True
    with SessionLocal() as db:
        costs = db.scalars(select(CostEntry).where(CostEntry.order_id == order.id, CostEntry.service == "gemini_photo_retouch")).all()
    assert len(costs) == 2

    # If the original has a face and the AI version doesn't, the AI version is thrown away.
    def faces(img):
        return [(10, 10, 50, 50)] if img.getpixel((5, 5))[0] < 240 else []

    monkeypatch.setattr(photo_enhance, "detect_faces", faces)
    _, info = photo_enhance.enhance(_photo((200, 150, 120)), "bride", use_ai=True)
    assert info["ai"] is False and "face not found" in info["ai_error"]


def test_demo_weddings_have_regional_portraits(client):
    import pytest

    from app.services import demo, demo_art, export

    if not export.chrome_binary():
        pytest.skip("Chrome/Chromium not installed")
    demo.ensure_demo()
    for lang in demo.DEMOS:
        order = demo.demo_order(lang)
        page = client.get(f"/demo/{lang}").text
        for role in ("bride", "groom", "family"):
            assert f"/e/{order.rsvp_slug}/portrait/{role}" in page, (lang, role)
    # Christian brides are drawn without bindi/sindoor.
    assert demo_art.REGIONS["kerala_christian"]["bride"].bindi is False
    demo.ensure_demo_portraits()  # idempotent: nothing duplicated
    with SessionLocal() as db:
        o = db.get(Order, demo.demo_order("hi").id)
        assert len([a for a in o.assets if a.kind == "portrait" and not a.deleted_at]) == 3


def test_custom_demo_photos_replace_illustrations(client):
    import pytest

    from app.services import demo, export

    if not export.chrome_binary():
        pytest.skip("Chrome/Chromium not installed")
    demo.ensure_demo()
    for lang in ("en", "hi", "ta"):
        with SessionLocal() as db:
            o = db.get(Order, demo.demo_order(lang).id)
            shown = {a.card_key: a for a in o.assets if a.kind == "portrait" and not a.deleted_at}
        custom = demo._custom_photo(lang, "bride") is not None
        assert bool((shown["bride"].meta or {}).get("source")) == custom, lang
        if custom:  # your bride/groom photos are enhanced + vibrant; the ready-made couple frame is used as-is
            assert shown["bride"].meta["enhanced"] is True and shown["family"].meta["enhanced"] is False
    before = len([a for a in o.assets if a.kind == "portrait"])
    demo.ensure_demo_portraits()  # unchanged files: nothing re-done
    with SessionLocal() as db:
        assert len([a for a in db.get(Order, o.id).assets if a.kind == "portrait"]) == before


def test_demo_cast_generator_with_stub_ai(tmp_path, monkeypatch):
    """The cast script without calling Gemini: every person + family is made and installed."""
    import importlib.util

    from PIL import Image

    spec = importlib.util.spec_from_file_location("cast", "scripts/make_demo_cast_ai.py")
    cast = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cast)
    Image.new("RGB", (300, 400), (200, 30, 40)).save(tmp_path / "bride.jpg")
    Image.new("RGB", (300, 400), (240, 230, 210)).save(tmp_path / "groom.jpg")
    calls = []

    def fake_generate(client, prompt, refs, aspect):
        calls.append((prompt[:20], len(refs), aspect))
        return Image.new("RGB", (400, 300) if aspect == "4:3" else (300, 400), (len(calls) * 20, 100, 150))

    monkeypatch.setattr(cast, "generate", fake_generate)
    out = cast.make_cast(client=None, demo_dir=tmp_path)
    assert set(out) == {"bride", "groom", "family"} and all(p.exists() for p in out.values())
    assert {p.stem for p in (tmp_path / "cast").iterdir()} == set(cast.CAST)
    assert calls[0][1] == 1 and calls[-1][1] == len(cast.CAST)  # bride styled on the old photo; family uses everyone
    assert (tmp_path / "previous" / "bride.jpg").exists()  # old photos kept


def create_event(client, event, **overrides):
    from app import events

    t = events.TYPES[event]
    data = {"event_type": event, "bride_name": t.demo[0], "groom_name": t.demo[1], "occasion_detail": t.demo[2],
            "language": "en", "style": t.styles[0], "wedding_date": WEDDING, "wedding_time": "18:00",
            "venue_name": "Grand Banquet", "city": "Pune", **overrides}
    return client.post("/create", data=data, follow_redirects=False)


def test_occasions_catalogue_pages(client):
    from app import events

    page = client.get("/occasions").text
    for c in events.CATEGORIES.values():
        assert c.name.replace("&", "&amp;") in page
    for key in events.TYPES:
        assert f"/create?event={key}" in page
    assert client.get("/samples/event/kids_birthday.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/samples/event/nope.jpg").status_code == 404
    form = client.get("/create?event=wedding_anniversary").text
    assert "Partner&#39;s name" in form and 'name="event_type" value="wedding_anniversary"' in form
    import re

    wedding_form = client.get("/create").text  # event styles exist on the page but start hidden for weddings
    assert re.search(r'data-style="kids_party" hidden', wedding_form) and not re.search(r'data-style="north_indian" hidden', wedding_form)
    assert "every occasion" in client.get("/").text


def test_kids_birthday_end_to_end(client):
    resp = create_event(client, "kids_birthday")
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    assert order.event_type == "kids_birthday" and order.occasion_detail == "5" and order.groom_name == ""
    assert order.status == OrderStatus.PREVIEW.value and order.rsvp_slug.startswith("aarav-kids-birthday")
    final = next(a for a in order.assets if a.kind == "final")
    assert final.qc["passed"], final.qc
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "Birthday Party" in page and "turns 5!" in page and "Event Details" in page
    assert "wedding of" not in page and "Wedding Invitation" not in page
    preview = client.get(f"/o/{order.token}/preview").text
    assert "Your invitation is ready" in preview and "Aarav &amp;" not in preview


def test_event_rules_jubilee_hindi_and_required_partner(client):
    resp = create_event(client, "wedding_anniversary", groom_name="")
    assert resp.status_code == 422 and "Partner&#39;s name is required" in resp.text
    order = get(create_event(client, "milestone_anniversary", occasion_detail="25").headers["location"].split("/")[2])
    assert "Silver Jubilee" in client.get(f"/e/{order.rsvp_slug}").text
    order = get(create_event(client, "satyanarayan_puja", language="hi").headers["location"].split("/")[2])
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "श्री सत्यनारायण पूजा" in page and "श्री गणेशाय नमः" in page and "प्रभु की असीम कृपा से" in page


def test_every_event_type_creates_a_working_invitation(client):
    from app import events
    from app.services import export

    for key, t in events.TYPES.items():
        resp = create_event(client, key)
        assert resp.status_code == 303, (key, resp.text[:600])
        order = get(resp.headers["location"].split("/")[2])
        final = next(a for a in order.assets if a.kind == "final")
        assert final.qc["passed"], (key, final.qc)
        page = client.get(f"/e/{order.rsvp_slug}")
        assert page.status_code == 200 and t.demo[0].replace("'", "&#39;") in page.text, key
        with SessionLocal() as db:
            html, _ = export.build_html(db.get(Order, order.id), "free")
        assert "event-headline" in html, key


def test_live_demos_for_every_occasion(client):
    from app import events
    from app.services import demo, export

    demo.ensure_demo()
    home = client.get("/").text
    assert home.count('class="lang-select occ-select"') == 2 and '<optgroup label="🪔 Religious Pujas">' in home
    for key, t in events.TYPES.items():
        resp = client.get(f"/demo?event={key}", follow_redirects=False)
        assert resp.status_code == 302, key
        page = client.get(resp.headers["location"]).text
        assert "Dear Mehta Family" in page and t.demo[0].replace("'", "&#39;") in page, key
        assert client.get(f"/demo/event/{key}/console").status_code == 200, key
    assert "Silver Jubilee" in client.get("/demo/event/milestone_anniversary").text
    assert client.get("/demo/event/bogus").status_code == 404
    assert '/demo/event/kids_birthday' in client.get("/occasions").text
    with SessionLocal() as db:
        events_count = db.scalars(select(Order).where(Order.source == "demo", Order.event_type != "wedding")).all()
    assert len(events_count) == len(events.TYPES)  # idempotent: one demo per type
    if export.chrome_binary():  # illustrated people where they fit, none for corporate
        kid = demo.demo_order("en", "kids_birthday")
        assert "/portrait/bride" in client.get(f"/e/{kid.rsvp_slug}").text
        shop = demo.demo_order("en", "grand_opening")
        assert "/portrait/" not in client.get(f"/e/{shop.rsvp_slug}").text


def test_create_page_has_occasion_picker(client):
    from app import events

    page = client.get("/create").text
    assert "What are you celebrating?" in page and 'class="occ-tab active" data-cat="wedding"' in page
    for key in events.TYPES:
        assert f'href="/create?event={key}"' in page
    event_page = client.get("/create?event=diwali_puja").text
    assert 'class="occ-tab active" data-cat="puja"' in event_page
    assert 'class="occ-type current" href="/create?event=diwali_puja"' in event_page


def test_create_form_switches_occasion_in_place(client):
    """One form for every occasion: the page carries each occasion's fields and labels for instant switching."""
    import json
    import re

    page = client.get("/create").text
    from app import events

    cfg = json.loads(re.search(r"const CFG = (\{.*?\});\n", page, re.S).group(1))

    assert set(cfg) == {"wedding", *events.TYPES}
    assert cfg["kids_birthday"]["primary"] == "Child's name" and cfg["kids_birthday"]["detail"] == "Turning (age)"
    assert cfg["wedding_anniversary"]["secondary_required"] is True and cfg["grand_opening"]["secondary"] == ""
    assert cfg["wedding"]["wedding"] is True and "kids_party" in cfg["kids_birthday"]["styles"]
    assert 'data-event="mundan"' in page and 'id="occ-selected"' in page
    # Server-side first render matches the chosen occasion (works without JavaScript too).
    bday = client.get("/create?event=kids_birthday").text
    assert 'name="event_type" value="kids_birthday"' in bday and '<span id="primary-label">Child&#39;s name</span>' in bday
    assert re.search(r'id="secondary-field"\s+hidden', bday)
    # Submitting the unified form as a wedding still works.
    order = create_instant(client, event_type="wedding")
    assert order.event_type == "wedding" and order.groom_name == "Rohan"


def test_audit_every_occasion_reads_right_for_guests(client, admin_auth):
    """Non-wedding invitations never fall back to wedding wording."""
    from app.services import export, invites, notify

    order = get(create_event(client, "kids_birthday").headers["location"].split("/")[2])
    with SessionLocal() as db:
        o = db.get(Order, order.id)
        o.package = "premium"
        db.commit()
        text = invites.whatsapp_text(o, Invitee(name="Mehta Family", code="xyz"))
        html, _ = export.build_html(o, "free")
        _, delivered = notify._messages(o, "delivered")
    assert "wedding of" not in text and "Aarav" in text and "birthday" in text
    assert '<div class="sub">Aarav</div>' in html  # no dangling "&" for single-honoree events
    assert "Shubh Vivah" not in delivered
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "Your wishes" in page and "the couple" not in page
    assert '<meta name="robots" content="noindex, nofollow">' in page
    status = client.get(f"/admin/orders/{order.id}", auth=admin_auth).text
    assert "Kids&#39; Birthday" in status and "Event date" in status


def test_audit_homepage_seo_and_sharing(client):
    from app.services import demo

    home = client.get("/").text
    assert "Free to create" in home and "Done-for-you wedding packages" in home and "Which occasions" in home
    assert 'class="tier-box popular"' in home and 'rel="icon"' in home and 'property="og:image"' in home
    robots = client.get("/robots.txt").text
    assert "Disallow: /e/" in robots and "Disallow: /i/" in robots and "/sitemap.xml" in robots
    sitemap = client.get("/sitemap.xml").text
    assert "/create?event=kids_birthday" in sitemap and "/occasions" in sitemap and "/o/" not in sitemap
    demo.ensure_demo()
    assert 'id="share-btn"' in client.get("/demo/en").text  # guests can share a live invitation
