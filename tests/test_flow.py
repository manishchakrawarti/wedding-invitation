import io
import hashlib
import hmac
import json
import re
import time
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

    client.post(f"/e/{slug}/details", data={"key": key, "hosts": "The Kapoor family", "gift_upi": "me@upi", "dress_haldi": "Yellow"})
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
    # cover + invitation (shloka, families) + main card + haldi card + celebrations + venue + closing
    assert len(re.findall(rb"/Type\s*/Page[^s]", free_pdf.content)) == 7
    free_img = client.get(f"{base}/image/free")
    assert free_img.headers["content-type"] == "image/jpeg" and _image_size(free_img) == (720, 900 * 7)
    assert client.get(f"{base}/pdf/1080").status_code == 403

    # Buy Full HD (₹9): 1080 unlocked, 2K still locked.
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    assert order.amount_paid == 900 and order.status == OrderStatus.DELIVERED.value
    status = client.get(f"/o/{order.token}").text
    assert "Your complete e-invite" in status and f"{base}/pdf/1080" in status and f"{base}/pdf/2k" not in status
    assert client.get(f"{base}/pdf/1080").content.startswith(b"%PDF")
    assert _image_size(client.get(f"{base}/image/1080")) == (1080, 1350 * 7)
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
    assert "/kids-birthday-invitation-card" in sitemap and "/occasions" in sitemap and "/o/" not in sitemap and "/demo/" not in sitemap
    demo.ensure_demo()
    assert 'id="share-btn"' in client.get("/demo/en").text  # guests can share a live invitation


# --- gifts (shagun) by UPI, for every occasion ------------------------------------

def _qr_png(text: str) -> bytes:
    import qrcode

    buf = io.BytesIO()
    qrcode.make(text, box_size=10, border=4).save(buf, "PNG")
    return buf.getvalue()


def _event_details(order_id: int):
    from app.models import EventDetails

    with SessionLocal() as db:
        return db.scalar(select(EventDetails).where(EventDetails.order_id == order_id))


def _instant_data(**overrides) -> dict:
    return {"bride_name": "Priya", "groom_name": "Rohan", "language": "en", "style": "north_indian",
            "wedding_date": WEDDING, "venue_name": "ITC Rajputana", "city": "Jaipur", **overrides}


def test_gift_details_on_create_show_on_invite_page_and_einvite(client):
    from app.services import export, gifts

    resp = create_event(client, "kids_birthday", gift_upi="aarav.papa@okhdfcbank", gift_phone="+91 98765 43210",
                        gift_name="Rakesh Mehta")
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    ev = _event_details(order.id)
    assert (ev.upi_id, ev.gift_phone, ev.gift_name) == ("aarav.papa@okhdfcbank", "9876543210", "Rakesh Mehta")

    page = client.get(f"/e/{order.rsvp_slug}").text.replace("&amp;", "&")
    assert "Send a gift" in page and "upi://pay?pa=aarav.papa%40okhdfcbank&pn=Rakesh%20Mehta" in page
    assert "+91 98765 43210" in page and "Rakesh Mehta" in page and f"/e/{order.rsvp_slug}/gift-qr" in page
    assert ">Copy</button>" in page  # (a "copy" key once rendered Python's dict.copy here)
    qr = client.get(f"/e/{order.rsvp_slug}/gift-qr")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
    assert gifts.decode_qr(qr.content).startswith("upi://pay?pa=aarav.papa%40okhdfcbank")

    # The PDF / long-image e-invite gets its own "Send a gift" page with the QR.
    with SessionLocal() as db:
        html, pages = export.build_html(db.get(Order, order.id), "free")
    assert "aarav.papa@okhdfcbank" in html and "+91 98765 43210" in html and 'class="gift-qr"' in html
    assert html.count('<section class="page') == pages


def test_gift_by_mobile_only_validation_and_hidden_when_empty(client):
    order = create_instant(client, gift_phone="98765 43210")
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "Send your blessings" in page and "+91 98765 43210" in page
    assert "upi://" not in page and "/gift-qr" not in page  # nothing to scan without a UPI ID or QR

    plain = create_instant(client)
    assert '<div class="shagun">' not in client.get(f"/e/{plain.rsvp_slug}").text

    bad = client.post("/create", data=_instant_data(gift_upi="not-an-upi", gift_phone="12345"))
    assert bad.status_code == 422 and "UPI ID doesn" in bad.text and "10-digit mobile number" in bad.text
    assert 'value="not-an-upi"' in bad.text  # what they typed is kept


def test_gift_qr_upload_reads_upi_id_and_can_be_changed(client):
    from app.services import gifts

    own_qr = _qr_png("upi://pay?pa=sharma.family@ybl&pn=Sharma%20Family&cu=INR")
    resp = client.post("/create", data=_instant_data(), files={"gift_qr": ("qr.png", own_qr, "image/png")},
                       follow_redirects=False)
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    ev = _event_details(order.id)
    assert ev.upi_id == "sharma.family@ybl" and ev.gift_name == "Sharma Family"  # read from their QR
    assert gifts.decode_qr(client.get(f"/e/{order.rsvp_slug}/gift-qr").content).startswith("upi://pay?pa=sharma.family@ybl")
    page = client.get(f"/e/{order.rsvp_slug}").text.replace("&amp;", "&")
    assert "upi://pay?pa=sharma.family%40ybl" in page  # the "Pay" button works too

    preview = client.get(f"/o/{order.token}/preview").text
    assert "Receive gifts" in preview and "sharma.family@ybl" in preview and f"/o/{order.token}/gift-qr" in preview

    # A QR that isn't a UPI payment QR is refused and nothing changes.
    r = client.post(f"/o/{order.token}/gift", files={"gift_qr": ("qr.png", _qr_png("https://example.com"), "image/png")},
                    follow_redirects=False)
    assert r.status_code == 303 and "gift_error=" in r.headers["location"]
    assert _event_details(order.id).upi_id == "sharma.family@ybl"

    # Switch to a mobile number and remove the QR.
    r = client.post(f"/o/{order.token}/gift", data={"gift_phone": "9123456780", "gift_qr_remove": "on"}, follow_redirects=False)
    assert "gift=saved" in r.headers["location"]
    ev = _event_details(order.id)
    assert ev.upi_id == "" and ev.gift_phone == "9123456780"
    assert client.get(f"/e/{order.rsvp_slug}/gift-qr").status_code == 404
    assert "+91 91234 56780" in client.get(f"/e/{order.rsvp_slug}").text


# --- photos are never silently lost ----------------------------------------------

def _portrait_roles(order_id: int) -> set[str]:
    with SessionLocal() as db:
        return {a.card_key for a in db.get(Order, order_id).live_assets("portrait")}


def test_photos_and_gift_qr_kept_after_a_form_error(client):
    files = [("bride_photo", ("b.jpg", _photo((200, 150, 120)), "image/jpeg")),
             ("groom_photo", ("g.jpg", _photo((90, 120, 160)), "image/jpeg")),
             ("gift_qr", ("qr.png", _qr_png("upi://pay?pa=asha.vivek@okaxis&pn=Asha"), "image/png"))]
    # The permission box is left unticked: the form comes back with an error...
    first = client.post("/create", data=_instant_data(bride_name="Asha", groom_name="Vivek"), files=files)
    assert first.status_code == 422 and "permission to use these photos" in first.text
    token = re.search(r'name="photo_stash" value="([^"]+)"', first.text).group(1)
    # ...but the photos stay chosen (shown as thumbnails) instead of being emptied by the browser.
    for name in ("bride", "groom", "gift_qr"):
        assert f"/create/kept/{token}/{name}" in first.text
        assert client.get(f"/create/kept/{token}/{name}").status_code == 200
    assert "/create/kept/" + token + "/family" not in first.text

    # Ticking the box and submitting again (no files re-chosen) keeps every photo.
    resp = client.post("/create", data=_instant_data(bride_name="Asha", groom_name="Vivek", photo_consent="on",
                                                    photo_stash=token), follow_redirects=False)
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    assert _portrait_roles(order.id) == {"bride", "groom"} and order.photo_consent
    assert _event_details(order.id).upi_id == "asha.vivek@okaxis"
    assert client.get(f"/create/kept/{token}/bride").status_code == 404  # the temporary copy is gone
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert f"/e/{order.rsvp_slug}/portrait/bride" in page and f"/e/{order.rsvp_slug}/portrait/groom" in page

    # Stash tokens can't reach outside the stash.
    assert client.get("/create/kept/..%2F..%2Fapp.db/bride").status_code == 404


def test_add_photos_after_creating_and_card_shown_in_preview(client):
    order = create_instant(client)
    preview = client.get(f"/o/{order.token}/preview").text
    assert "Photos on your invitation" in preview and "no photos yet" in preview
    # During the free preview the invite page still shows the (watermarked) card, never a bare page.
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert f'src="/e/{order.rsvp_slug}/invite"' in page and "Save the card" not in page
    card = client.get(f"/e/{order.rsvp_slug}/invite")
    proof = next(a for a in order.assets if a.kind == "proof" and a.card_key == "main")
    from app.services.storage import storage
    assert card.status_code == 200 and card.content == storage.read(proof.path)

    photo = [("bride_photo", ("b.jpg", _photo((200, 150, 120)), "image/jpeg"))]
    r = client.post(f"/o/{order.token}/photos", files=photo, follow_redirects=False)
    assert "photo_error=" in r.headers["location"]  # permission needed
    r = client.post(f"/o/{order.token}/photos", data={"photo_consent": "on"}, files=photo, follow_redirects=False)
    assert r.headers["location"].endswith("/preview?photos=saved#photos")
    assert _portrait_roles(order.id) == {"bride"}
    assert f"/e/{order.rsvp_slug}/portrait/bride" in client.get(f"/e/{order.rsvp_slug}").text
    preview = client.get(f"/o/{order.token}/preview").text
    assert f"/o/{order.token}/portrait/bride" in preview and client.get(f"/o/{order.token}/portrait/bride").status_code == 200


def test_stash_purge_removes_old_uploads(tmp_path):
    import os
    import time as _time

    from app.services.storage import LocalStorage

    store = LocalStorage(tmp_path)
    store.save("stash/abc/bride", b"x")
    store.save("stash/new/bride", b"y")
    old = _time.time() - 7 * 3600
    os.utime(tmp_path / "stash/abc/bride", (old, old))
    assert store.purge("stash/", 6 * 3600) == 1
    assert not (tmp_path / "stash/abc").exists() and store.exists("stash/new/bride")


# --- times: 12-hour (AM/PM) or 24-hour ------------------------------------------------

def test_clean_time_and_pretty_time_formats():
    from app.utils import clean_time, pretty_time

    assert [clean_time(x) for x in ("19:30", "7:30 PM", "7 pm", "12:05 am", "12 PM", "25:00", "13:00 PM", "7", "x", "")] == \
        ["19:30", "19:30", "19:00", "00:05", "12:00", "", "", "", "", ""]
    assert (pretty_time("19:30"), pretty_time("19:30", "24h"), pretty_time("00:15"), pretty_time("00:15", "24h")) == \
        ("7:30 PM", "19:30", "12:15 AM", "00:15")


def test_time_picker_and_24_hour_invitations(client):
    form = client.get("/create").text
    assert 'type="time"' not in form and 'name="time_format"' in form and 'class="tp-ap"' in form

    ampm = create_instant(client, wedding_time="19:30", fn_haldi="on", fn_haldi_date=WEDDING, fn_haldi_time="10:15")
    page = client.get(f"/e/{ampm.rsvp_slug}").text
    assert ampm.time_format == "12h" and "7:30 PM" in page and "10:15 AM" in page

    h24 = create_instant(client, wedding_time="19:30", time_format="24h", fn_haldi="on", fn_haldi_date=WEDDING,
                         fn_haldi_time="10:15")
    page = client.get(f"/e/{h24.rsvp_slug}").text
    assert h24.time_format == "24h" and "19:30" in page and "7:30 PM" not in page and "10:15 AM" not in page
    assert next(f for f in h24.functions if f["key"] == "wedding")["time"] == "19:30"

    # A broken time is dropped instead of breaking the cards.
    bad = create_instant(client, wedding_time="99:99")
    assert next(f for f in bad.functions if f["key"] == "wedding")["time"] == ""


def test_instant_download_paid_by_razorpay_me_unlocks_after_confirm(client, admin_auth, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "razorpay_me_url", "https://razorpay.me/@example")
    order = create_instant(client)
    r = client.post(f"/o/{order.token}/unlock", data={"res": "1080"}, follow_redirects=False)
    page = client.get(r.headers["location"]).text
    assert "enter exactly <strong>₹9</strong>" in page and 'data-copy="9"' in page and "unlock my download" in page
    payment_id = re.search(r"/pay/claim/(\d+)", page).group(1)
    assert client.get(f"/o/{order.token}/pay/status/{payment_id}").json() == {"paid": False}

    client.post(f"/o/{order.token}/pay/claim/{payment_id}", data={"reference": "pay_TEST12345678"})
    waiting = client.get(f"/o/{order.token}/pay?purpose=full").text
    assert "Full HD download unlocks" in waiting and "design starts" not in waiting
    assert f"/o/{order.token}/pay/status/{payment_id}" in waiting  # the page checks by itself

    client.post(f"/admin/payments/{payment_id}/confirm", auth=admin_auth)
    assert client.get(f"/o/{order.token}/pay/status/{payment_id}").json() == {"paid": True}
    order = get(order.token)
    assert order.status == OrderStatus.DELIVERED.value and order.amount_paid == 900
    assert client.get(f"/o/{order.token}/einvite/image/1080").status_code in (200, 503)  # 503 only without Chrome


def test_venue_heading_fits_every_occasion_and_language(client):
    resp = create_event(client, "wedding_anniversary", language="hi")
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "कार्यक्रम स्थल" in page and "यहाँ पहुँचें" in page and "विवाह स्थल" not in page
    assert "Create one for your own celebration" in page and "family's wedding" not in page

    english = create_instant(client)
    page = client.get(f"/e/{english.rsvp_slug}").text
    assert "find your way" in page and "The Venue" in page and "Create one for your family's wedding" in page


def test_send_personal_invite_by_whatsapp_sms_and_pdf(client):
    from app.services import export, invites

    order = create_instant(client, hosts="The Sharma family")
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    status = client.get(f"/o/{order.token}").text
    assert "Send a personal invitation" in status and f'value="{order.customer_name}"' in status  # sender prefilled

    # Bad numbers are refused, for the guest and for the sender.
    for bad in ({"name": "X", "phone": "12345"}, {"name": "X", "sender_phone": "000"}, {"name": " "}):
        resp = client.post(f"/o/{order.token}/guests", data=bad, follow_redirects=False)
        assert "send_error=" in resp.headers["location"]
    assert _invitees(order.id) == []

    resp = client.post(f"/o/{order.token}/guests", data={
        "name": "Mehta Family", "phone": "98765 43210", "sender_name": "Rajesh Sharma", "sender_phone": "+91 91234-56780",
    }, follow_redirects=False)
    [mehta] = _invitees(order.id)
    assert resp.headers["location"].endswith(f"?sent={mehta.id}#send")
    assert mehta.phone == "919876543210" and mehta.sent_by == "Rajesh Sharma" and mehta.sender_phone == "919123456780"

    page = client.get(resp.headers["location"]).text.replace("&amp;", "&")
    assert "Ready. Tap" in page and "wa.me/919876543210?text=" in page and "sms:+919876543210?&body=" in page
    assert f"/o/{order.token}/guests/{mehta.id}/invite.pdf" in page
    with SessionLocal() as db:
        o = db.get(Order, order.id)
        text, sms = invites.whatsapp_text(o, o.invitees[0]), invites.sms_text(o, o.invitees[0])
    assert "Dear Mehta Family" in text and f"/i/{mehta.code}" in text and "— Rajesh Sharma, +91 91234 56780" in text
    assert "Dear Mehta Family" in sms and f"/i/{mehta.code}" in sms and "Rajesh Sharma" in sms and len(sms) < 300

    # The guest's page greets them and says who it's from, with a way to reply.
    guest = client.get(f"/i/{mehta.code}").text
    assert "Dear Mehta Family" in guest and "Invitation sent by: <strong>Rajesh Sharma</strong>" in guest
    assert 'href="tel:+919123456780"' in guest and "wa.me/919123456780" in guest
    assert "Invitation sent by" not in client.get(f"/e/{order.rsvp_slug}").text  # the general link stays general

    # The next invite is from the same person; an empty mobile hides it; a guest abroad keeps their country code.
    assert 'value="Rajesh Sharma"' in client.get(f"/o/{order.token}").text
    client.post(f"/o/{order.token}/guests", data={"name": "Uncle in London", "phone": "+44 7700 900123",
                                                  "sender_name": "Rajesh Sharma", "sender_phone": ""})
    uncle = _invitees(order.id)[1]
    assert uncle.phone == "447700900123" and uncle.sender_phone == ""
    assert "tel:" not in client.get(f"/i/{uncle.code}").text.split("Invitation sent by", 1)[1].split("</section>")[0]

    # Tapping send marks it sent; another order can't touch these guests.
    assert client.post(f"/o/{order.token}/guests/{mehta.id}/sent").json() == {"ok": True}
    assert _invitees(order.id)[0].sent_at is not None
    other = create_instant(client, bride_name="Asha")
    assert client.post(f"/o/{other.token}/guests/{mehta.id}/sent").status_code == 404
    assert client.get(f"/o/{other.token}/guests/{mehta.id}/invite.pdf").status_code == 404

    # The personal e-invite: their name on the cover, "Dear …", who sent it and a QR to their own link.
    with SessionLocal() as db:
        o = db.get(Order, order.id)
        html, _ = export.build_html(o, "1080", invitee=o.invitees[0])
        plain, _ = export.build_html(o, "1080")
    assert "Mehta Family" in html and "Dear Mehta Family" in html and "Invitation sent by" in html
    assert f"/i/{mehta.code}" in html and "Mehta Family" not in plain
    if export.chrome_binary():
        pdf = client.get(f"/o/{order.token}/guests/{mehta.id}/invite.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    client.post(f"/o/{order.token}/guests/{uncle.id}/delete")
    assert [i.name for i in _invitees(order.id)] == ["Mehta Family"]
    assert client.get(f"/i/{uncle.code}").status_code == 404


def test_console_guests_carry_the_sender(client, admin_auth):
    order = place_order(client, package="premium")
    order = pay(client, order)
    client.post(f"/admin/orders/{order.id}/send-proof", auth=admin_auth)
    client.post(f"/o/{order.token}/proof/approve")
    slug, key = order.rsvp_slug, order.token
    console = client.get(f"/e/{slug}/guests?key={key}").text
    assert 'name="sender_name"' in console
    resp = client.post(f"/e/{slug}/guests/add", data={"key": key, "guests": "Sharma Family, 98765 43210",
                                                      "sender_name": "Sunita Kapoor", "sender_phone": "9123456780"})
    assert "Added 1 guest(s)" in resp.text and "sms:+919876543210?&amp;body=" in resp.text and "Share PDF" in resp.text
    [sharma] = _invitees(order.id)
    assert sharma.sent_by == "Sunita Kapoor" and sharma.sender_phone == "919123456780"
    assert "Invitation sent by: <strong>Sunita Kapoor</strong>" in client.get(f"/i/{sharma.code}").text


def test_telegram_bot_alerts_and_pdfs(client, admin_auth, monkeypatch):
    """Owner alerts, customer PDF and a guest's personal PDF over the free Telegram bot (API faked)."""
    from app.config import settings
    from app.models import TelegramChat
    from app.services import export, telegram

    calls = []

    def fake_call(method, data=None, files=None, timeout=60):
        calls.append((method, dict(data or {}), {k: v[0] for k, v in (files or {}).items()}))
        return {"username": "InviteAllBot"} if method == "getMe" else {}

    monkeypatch.setattr(telegram, "_call", fake_call)
    monkeypatch.setattr(settings, "telegram_bot_token", "123:test-token")
    monkeypatch.setattr(telegram, "_recent", {})

    def tg(text, chat=555, secret=None):
        return client.post("/webhooks/telegram", json={"message": {"chat": {"id": chat}, "from": {"first_name": "Manish"}, "text": text}},
                           headers={"X-Telegram-Bot-Api-Secret-Token": secret or telegram.webhook_secret()})

    assert tg("/start hi", secret="wrong").status_code == 403

    # Owner: the admin page links to the bot; opening it connects alerts.
    page = client.get("/admin", auth=admin_auth).text.replace("&amp;", "&")
    assert f"https://t.me/InviteAllBot?start={telegram.owner_payload()}" in page
    assert tg("/start admin_forged").status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(TelegramChat)).all() == []
    tg(f"/start {telegram.owner_payload()}", chat=777)
    assert "alerts are connected" in calls[-1][1]["text"]
    assert "Telegram alerts go to: Manish" in client.get("/admin", auth=admin_auth).text

    # Customer: link on the pay page; a claimed payment alerts the owner on Telegram.
    order = create_instant(client)
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    monkeypatch.setattr(settings, "razorpay_me_url", "https://razorpay.me/@test")
    client.get(f"/o/{order.token}/pay")
    payment = get(order.token).payments[-1]
    client.post(f"/o/{order.token}/pay/claim/{payment.id}", data={"reference": "pay_TEST123"})
    assert any(c[1].get("chat_id") == "777" and "pay_TEST123" in c[1].get("text", "") for c in calls)
    pay_page = client.get(f"/o/{order.token}/pay").text.replace("&amp;", "&")
    assert f"https://t.me/InviteAllBot?start=o_{order.token}" in pay_page

    # Opening it connects the chat; once confirmed, the Full HD PDF arrives there.
    calls.clear()
    tg(f"/start o_{order.token}", chat=555)
    client.post(f"/admin/payments/{payment.id}/confirm", auth=admin_auth)
    assert get(order.token).status == OrderStatus.DELIVERED.value
    sent = [c for c in calls if c[1].get("chat_id") == "555"]
    assert sent, calls
    if export.chrome_binary():
        assert any(c[0] == "sendDocument" and c[2]["document"].endswith(".pdf") and "is ready!" in c[1]["caption"] for c in sent)

    # A guest: Telegram share button for the family, and a bot link on the guest's page for their PDF.
    client.post(f"/o/{order.token}/guests", data={"name": "Mehta Family", "sender_name": "Rajesh"})
    [mehta] = _invitees(order.id)
    assert "t.me/share/url?url=" in client.get(f"/o/{order.token}").text
    assert f"https://t.me/InviteAllBot?start=i_{mehta.code}" in client.get(f"/i/{mehta.code}").text.replace("&amp;", "&")
    calls.clear()
    tg(f"/start i_{mehta.code}", chat=888)
    first = len(calls)
    tg(f"/start i_{mehta.code}", chat=888)  # a second tap within minutes doesn't render again
    assert len(calls) == first
    assert calls[0][0] == "sendDocument" and calls[0][2]["document"].endswith(".jpg")  # their personal card first
    assert "Mehta Family" in calls[0][1]["caption"]

    # Anything else gets the shop's auto-reply, e.g. an order's status.
    calls.clear()
    tg(f"status of {order.public_id}?", chat=999)
    assert "Delivered" in calls[-1][1]["text"]


def test_personal_cards_while_creating_for_every_occasion(client):
    """Free preview: name a guest, get their own card with their name on it, send it on any free channel;
    the same link becomes the full invite page once a size is bought."""
    from PIL import Image

    for event in ["wedding", "kids_birthday", "griha_pravesh", "grand_opening"]:
        order = create_instant(client) if event == "wedding" else get(create_event(client, event).headers["location"].split("/")[2])
        assert order.status == OrderStatus.PREVIEW.value
        page = client.get(f"/o/{order.token}/preview").text
        assert "Send a personal invitation" in page and "Free now: their personal card" in page, event

        resp = client.post(f"/o/{order.token}/guests", data={"name": "Sharma Family", "phone": "9876543210",
                                                             "email": "sharma@example.com", "sender_name": "Rajesh"},
                           follow_redirects=False)
        assert resp.headers["location"].startswith(f"/o/{order.token}/preview?sent="), event
        sharma = _invitees(order.id)[-1]
        assert sharma.email == "sharma@example.com"
        page = client.get(resp.headers["location"]).text.replace("&amp;", "&")
        for channel in ("wa.me/919876543210?text=", "sms:+919876543210", "t.me/share/url?url=", "facebook.com/sharer/sharer.php?u=",
                        "mailto:sharma@example.com?subject=", "Share card", f"/o/{order.token}/guests/{sharma.id}/card.jpg"):
            assert channel in page, (event, channel)

        # Their card: free size with their name on it (and the small credit), no QR yet.
        card = client.get(f"/o/{order.token}/guests/{sharma.id}/card.jpg")
        assert card.status_code == 200 and Image.open(io.BytesIO(card.content)).size == (720, 900), event
        assert client.get(f"/i/{sharma.code}/card.jpg").content == card.content

        # Their link shows that card while the family is on the free preview.
        guest = client.get(f"/i/{sharma.code}").text
        assert f"/i/{sharma.code}/card.jpg" in guest and "Sharma Family" in guest and 'id="doors"' not in guest
        assert "Free preview" not in guest and "Invitation sent by: <strong>Rajesh</strong>" in guest, event

    # After buying Full HD the same link is the full invite page, and the card is Full HD with a QR.
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    assert order.status == OrderStatus.DELIVERED.value
    full = client.get(f"/i/{sharma.code}").text
    assert 'id="doors"' in full and f'og:image" content="http://testserver/i/{sharma.code}/card.jpg"' in full
    card = client.get(f"/o/{order.token}/guests/{sharma.id}/card.jpg")
    assert Image.open(io.BytesIO(card.content)).size == (1080, 1350)

    # Bad email is refused; another order can't fetch this guest's card.
    resp = client.post(f"/o/{order.token}/guests", data={"name": "X", "email": "not-an-email"}, follow_redirects=False)
    assert "send_error=" in resp.headers["location"]
    other = create_instant(client, bride_name="Asha")
    assert client.get(f"/o/{other.token}/guests/{sharma.id}/card.jpg").status_code == 404


def test_seo_landing_pages_sitemap_and_meta(client):
    from app import seo
    from app.events import TYPES

    pages = seo.pages()
    assert len(pages) == 1 + 9 + 5 + len(TYPES)  # wedding, 9 language weddings, 5 wedding styles, every occasion
    sitemap = client.get("/sitemap.xml").text
    titles, descriptions = set(), set()
    for p in pages.values():
        assert f"<loc>http://testserver{p.path}</loc>" in sitemap or f"{p.path}</loc>" in sitemap, p.path
        import html as htmllib

        html = htmllib.unescape(client.get(p.path).text)
        title = re.search(r"<title>([^<]*)</title>", html).group(1)
        desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        assert len(title) <= 70 and p.h1 in html and f'href="{p.create_url}"' in html, p.path
        assert f'<link rel="canonical" href="http://localhost:8000{p.path}">' in html or 'rel="canonical"' in html
        assert '"@type": "FAQPage"' in html and '"@type": "BreadcrumbList"' in html
        titles.add(title)
        descriptions.add(desc)
    assert len(titles) == len(pages) and len(descriptions) == len(pages)  # every page is its own

    # The occasion page and the footer link to them; the creator's occasion URLs stay out of the index.
    assert 'href="/griha-pravesh-invitation-card"' in client.get("/occasions").text
    home = client.get("/").text
    assert 'href="/hindi-wedding-invitation-card"' in home and '"@type": "Organization"' in home
    assert "Free Online Invitation Card Maker" in home and 'rel="icon" href="/favicon.ico"' in home
    assert '<meta name="robots" content="noindex, follow">' in client.get("/create?event=mundan").text
    assert "noindex" not in client.get("/create").text
    assert client.get("/favicon.ico").headers["content-type"] == "image/x-icon"
    assert client.get("/site.webmanifest").json()["icons"]
    assert client.get("/no-such-page").status_code == 404


def test_instant_try_preview_prefill_and_selfie_frame(client):
    from PIL import Image

    from app.routes import public

    # "See your card in 1 second": a card with the typed names, for weddings and any occasion
    home = client.get("/").text
    assert 'id="try-form"' in home and "See <span" in home and '"kids_birthday": ["Child' in home
    card = client.get("/try.jpg", params={"a": "Priyanka", "b": "Manish", "date": "2026-12-21"})
    assert card.status_code == 200 and card.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(card.content)).size == (540, 675)
    other = client.get("/try.jpg", params={"event": "griha_pravesh", "a": "The Gupta Family"})
    assert other.status_code == 200 and other.content != card.content
    # junk is cleaned, not rendered or crashed on
    assert client.get("/try.jpg", params={"style": "<script>", "lang": "zz", "event": "nope", "date": "soon",
                                          "a": "x" * 5000}).status_code == 200
    public._try_hits.clear()
    public._try_hits["testclient"] = [time.time()] * public.TRY_PER_10_MIN
    assert client.get("/try.jpg").status_code == 429
    public._try_hits.clear()

    # "Make it mine" carries the names and date into the create form (no preview panel over the form)
    page = client.get("/create", params={"bride_name": "Priyanka", "groom_name": "Manish", "wedding_date": WEDDING}).text
    assert 'value="Priyanka"' in page and 'value="Manish"' in page and f'value="{WEDDING}"' in page and 'id="live-prev"' not in page
    assert 'value="Aarav"' in client.get("/create", params={"event": "kids_birthday", "bride_name": "Aarav"}).text

    # Guests get the "I'm invited" selfie frame on the invite page, in the card's language
    order = create_instant(client, language="en")
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert 'id="selfie"' in page and "I&#39;m invited! 💌" in page and 'capture="user"' in page


def test_admin_stats_count_people_not_bots(client, admin_auth):
    from app.services import stats

    stats.flush()
    before = client.get("/admin/stats", auth=admin_auth)
    assert before.status_code == 200 and "Visitors per day" in before.text
    with stats._lock:
        stats._pending.clear()  # other tests' page views
    browser = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Mobile Safari"}
    fresh = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(client.app)
    first = fresh.get("/?utm_source=Instagram", headers=browser)
    assert stats.VISITOR_COOKIE in first.cookies  # counted once, then remembered for the day
    fresh.get("/griha-pravesh-invitation-card", headers=browser)
    fresh.get("/try.jpg", headers=browser)
    client.get("/", headers={"User-Agent": "Googlebot/2.1"})  # bots don't count
    with stats._lock:
        pending = dict(stats._pending)
    today = date.today().isoformat()
    assert pending.get((today, "visitor", "all")) == 1 and pending.get((today, "source", "instagram")) == 1
    assert pending.get((today, "view", "/griha-pravesh-invitation-card")) == 1 and pending.get((today, "try", "all")) == 1
    assert not any(k[1] == "view" and k[2].startswith("/admin") for k in pending)

    order = create_instant(client)
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    pay(client, get(order.token))
    page = client.get("/admin/stats", auth=admin_auth).text
    assert "instagram" in page and "/griha-pravesh-invitation-card" in page
    revenue = re.search(r'Revenue</div><div class="v">([^<]*)</div>', page).group(1)
    assert revenue.startswith("₹") and revenue != "₹0"  # other tests' paid orders count too


def test_gallery_shows_only_cards_families_chose_to_share(client, admin_auth):
    from app.routes import public

    shy = create_instant(client, bride_name="Shy")
    proud = create_instant(client, bride_name="Proud", gallery_ok="on")
    assert get(proud.token).gallery_ok and not get(shy.token).gallery_ok
    for o in (shy, proud):
        client.post(f"/o/{o.token}/unlock", data={"res": "1080"})
        pay(client, get(o.token))
    page = client.get("/gallery").text
    assert f"/gallery/{proud.public_id}.jpg" in page and f"/gallery/{shy.public_id}.jpg" not in page
    assert client.get(f"/gallery/{proud.public_id}.jpg").headers["content-type"] == "image/jpeg"
    assert client.get(f"/gallery/{shy.public_id}.jpg").status_code == 404
    assert "/gallery" in client.get("/sitemap.xml").text

    # the family can take it out (and put it back) from their order page; the owner can hide it in admin
    assert "Remove it from the gallery" in client.get(f"/o/{proud.token}").text
    client.post(f"/o/{proud.token}/gallery", data={"show": "0"})
    assert f"/gallery/{proud.public_id}.jpg" not in client.get("/gallery").text
    client.post(f"/o/{shy.token}/gallery", data={"show": "1"})
    assert f"/gallery/{shy.public_id}.jpg" in client.get("/gallery").text
    client.post(f"/admin/orders/{shy.id}/gallery-hide", auth=admin_auth)
    assert client.get(f"/gallery/{shy.public_id}.jpg").status_code == 404

    # the counter appears only once there's a number worth showing
    public._made_cache.update(at=time.time(), n=12)
    assert "invitations made" not in client.get("/").text
    public._made_cache.update(at=time.time(), n=1234)
    assert "1,234 invitations made" in client.get("/").text
    public._made_cache.update(at=0.0)


def test_wording_library_pages(client):
    from app import wording
    from app.events import TYPES

    pages = wording.pages()
    assert len(pages) == 1 + len(TYPES) and all(p.count >= 6 for p in pages.values())
    index = client.get("/wording").text
    assert all(p.path in index for p in pages.values())
    page = client.get("/wording/griha-pravesh-invitation-message").text
    assert "गृह प्रवेश" in page and "<mark>[" in page and "wa.me/?text=" in page and 'href="/create?event=griha_pravesh"' in page
    assert '"@type": "BreadcrumbList"' in page and "Griha Pravesh Invitation Message in Hindi" in page
    wedding = client.get("/wording/wedding-invitation-message").text
    assert "Wedding card shayari" in wedding and "श्री गणेशाय नमः" in wedding
    assert client.get("/wording/not-a-page").status_code == 404
    assert "/wording/griha-pravesh-invitation-message" in client.get("/griha-pravesh-invitation-card").text
    assert "/wording/wedding-invitation-message" in client.get("/sitemap.xml").text


def test_hindi_website_switch(client):
    from fastapi.testclient import TestClient

    from app import ui_text

    visitor = TestClient(client.app)
    page = visitor.get("/?ui=hi")
    assert page.cookies.get(ui_text.COOKIE) == "hi" and '<html lang="hi">' in page.text
    assert "सिर्फ़ एक कार्ड नहीं," in page.text and "🌐 English" in page.text and "Not just a card." not in page.text
    assert int(page.headers["content-length"]) == len(page.content)
    create = visitor.get("/create?event=griha_pravesh").text  # remembered from the cookie
    assert "गृह प्रवेश का निमंत्रण बनाएँ" in create and "✨ मेरा निमंत्रण बनाएँ" in create
    assert 'placeholder="जैसे: जयपुर"' in create or "जैसे:" in create
    # guest invite pages keep the card's own language; admin stays English
    order = create_instant(client)
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    assert '<html lang="en">' in visitor.get(f"/e/{order.rsvp_slug}").text
    visitor.get("/?ui=en")
    assert "Not just a card." in visitor.get("/").text and "🌐 हिन्दी" in visitor.get("/").text


def test_homepage_feature_cards(client):
    page = client.get("/?ui=en").text
    section = page[page.index('id="experience"'):page.index('id="occasions"')]
    assert section.count('<div class="card">') == 10
    for title in ("selfie frame", "See it as you type", "230 ready messages", "PDF, long image &amp; 4K print"):
        assert title in section, title
    assert "(Premium)." not in section and "a real designer checks every invite" not in section


def test_create_with_family_details_and_guest_list(client):
    """What traditional cards carry (blessing, welcomers, children's line, contacts, gift note, dress codes)
    and a guest list pasted while creating, so every guest's named card is ready to send."""
    from app.services import export

    resp = client.post("/create", data={
        "bride_name": "Priya", "groom_name": "Rohan", "language": "en", "style": "north_indian", "wedding_date": WEDDING,
        "venue_name": "ITC Rajputana", "city": "Jaipur", "hosts": "The Sharma family", "customer_name": "Rakesh Sharma",
        "blessing_line": "Late Shri Ram Prasad Sharma", "welcomers": "Chacha-Chachi and all the family",
        "kids_note": "Do come to my didi's wedding! — Aarav", "contact_name_1": "Rakesh Sharma", "contact_phone_1": "98765 43210",
        "contact_name_2": "Rohit", "gift_note": "blessings_only", "dress_main": "Traditional",
        "fn_haldi": "on", "fn_haldi_date": WEDDING, "fn_haldi_dress": "Yellow",
        "guest_list": "Mehta Family, 9123456780\nMeena Bua\n\nRahul Verma",
    }, follow_redirects=False)
    assert resp.status_code == 303, resp.text[:800]
    order = get(resp.headers["location"].split("/")[2])
    with SessionLocal() as db:
        ev = db.get(Order, order.id).event
        assert ev.welcomers.startswith("Chacha") and ev.kids_note.startswith("Do come") and ev.gift_note == "blessings_only"
        assert ev.rsvp_contacts == [{"name": "Rakesh Sharma", "phone": "919876543210"}, {"name": "Rohit", "phone": ""}]
        assert ev.dress_codes == {"wedding": "Traditional", "haldi": "Yellow"} and ev.blessing_line.startswith("Late")
    guests = _invitees(order.id)
    assert [g.name for g in guests] == ["Mehta Family", "Meena Bua", "Rahul Verma"]
    assert guests[0].phone == "919123456780" and guests[0].sent_by == "Rakesh Sharma"

    # the preview page lists them ready to send with their own card
    preview = client.get(f"/o/{order.token}/preview").text
    assert "Mehta Family" in preview and f"/o/{order.token}/guests/{guests[0].id}/card.jpg" in preview

    # shown on the invite page and in the PDF once live
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "Eagerly awaiting you" in page and "Chacha-Chachi" in page and "Do come to my didi" in page
    assert 'href="tel:+919876543210"' in page and "Your blessings are our gift" in page and "Late Shri Ram Prasad" in page
    with SessionLocal() as db:
        html, _ = export.build_html(db.get(Order, order.id), "1080")
    assert "Chacha-Chachi" in html and "+91 98765 43210" in html

    # a wrong contact number is refused, with the form kept
    bad = client.post("/create", data={"bride_name": "A", "groom_name": "B", "language": "en", "style": "north_indian",
                                       "wedding_date": WEDDING, "venue_name": "X", "contact_phone_1": "12"})
    assert bad.status_code == 422 and "Contact number 1" in bad.text and 'id="wz-next"' in bad.text


def test_lord_ganesha_on_hindu_invitations_only(client):
    from types import SimpleNamespace as NS

    from app.services import export
    from app.services.cards import cards_for_order, shows_ganesha
    from app.services.overlay import Emblem

    def card_has_ganesha(**kw):
        o = NS(language="en", style="north_indian", is_wedding=True, event_type="wedding", show_ganesha=True, bride_name="A",
               groom_name="B", bride_name_local="", groom_name_local="", bride_family="", groom_family="", package="instant",
               addons=[], functions=[{"key": "wedding", "time": "19:00"}], wedding_date=date(2026, 12, 12), venue_name="V",
               venue_address="", city="", time_format="12h", occasion_detail="", event=None)
        for k, v in kw.items():
            setattr(o, k, v)
        main = cards_for_order(o)[0]
        return shows_ganesha(o), any(isinstance(i, Emblem) for i in main.items)

    assert card_has_ganesha() == (True, True)
    assert card_has_ganesha(style="muslim_nikah") == (False, False)
    assert card_has_ganesha(style="christian") == (False, False)
    assert card_has_ganesha(language="pa") == (False, False)  # Sikh weddings open with ੴ
    assert card_has_ganesha(show_ganesha=False) == (False, False)  # the family turned it off
    assert card_has_ganesha(show_ganesha=None) == (True, True)  # orders from before the option: on
    assert card_has_ganesha(is_wedding=False, event_type="griha_pravesh", occasion_detail="Lunch") == (True, True)
    assert card_has_ganesha(is_wedding=False, event_type="kids_birthday", occasion_detail="5") == (False, False)

    # invite page and booklet: Ganesha, the shloka and the closing page; turned off when the family unticks it
    order = create_instant(client)
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert 'class="ganesha-hero"' in page
    with SessionLocal() as db:
        html, pages = export.build_html(db.get(Order, order.id), "1080")
    assert "वक्रतुण्ड महाकाय" in html and 'class="ganesha"' in html and "Your presence will make our celebration complete" in html
    plain = create_instant(client, bride_name="Jain", ganesha="off")
    assert get(plain.token).show_ganesha is False
    client.post(f"/o/{plain.token}/unlock", data={"res": "1080"})
    plain = pay(client, get(plain.token))
    assert 'class="ganesha-hero"' not in client.get(f"/e/{plain.rsvp_slug}").text
    assert "Lord Ganesha" in client.get("/create").text


def test_bride_and_groom_degree_parents_and_home(client):
    from app.services import export
    from app.services.cards import cards_for_order, family_line

    resp = client.post("/create", data={
        "bride_name": "Priyanka", "groom_name": "Manish", "language": "en", "style": "north_indian", "wedding_date": WEDDING,
        "venue_name": "ITC Rajputana", "city": "Jaipur",
        "bride_degree": "B.Tech · Software Engineer", "bride_father": "Shri Rakesh Sharma", "bride_mother": "Smt. Sunita Sharma",
        "bride_home": "Jaipur", "groom_degree": "MBA", "groom_father": "Shri Vikram Mehta", "groom_home": "Lucknow",
    }, follow_redirects=False)
    order = get(resp.headers["location"].split("/")[2])
    with SessionLocal() as db:
        o = db.get(Order, order.id)
        assert family_line(o, "bride") == "Daughter of Smt. Sunita Sharma & Shri Rakesh Sharma, Jaipur"
        assert family_line(o, "groom") == "Son of Shri Vikram Mehta, Lucknow"
        texts = [i.text for i in cards_for_order(o)[0].items if hasattr(i, "text")]
        assert "B.Tech · Software Engineer" in texts and "MBA" in texts and family_line(o, "bride") in texts
        qc = next(a for a in o.live_assets("final") if a.card_key == "main").qc
        assert next(c for c in qc["checks"] if c["name"] == "text_match")["status"] == "pass"
        # Hindi: एवं between the parents, निवासी before the home town
        o.language = "hi"
        assert family_line(o, "bride") == "सुपुत्री Smt. Sunita Sharma एवं Shri Rakesh Sharma, निवासी Jaipur"
        db.rollback()
    client.post(f"/o/{order.token}/unlock", data={"res": "1080"})
    order = pay(client, get(order.token))
    page = client.get(f"/e/{order.rsvp_slug}").text
    assert "B.Tech · Software Engineer" in page and "Daughter of Smt. Sunita Sharma &amp; Shri Rakesh Sharma, Jaipur" in page
    with SessionLocal() as db:
        html, _ = export.build_html(db.get(Order, order.id), "1080")
    assert "Son of Shri Vikram Mehta, Lucknow" in html and "B.Tech · Software Engineer" in html
    assert "Bride&#39;s side" in client.get("/create").text or "Bride's side" in client.get("/create").text


def test_installable_app_and_android_asset_links(client, monkeypatch):
    from app.config import settings

    m = client.get("/site.webmanifest").json()
    assert m["display"] == "standalone" and m["scope"] == "/" and m["id"] == "/"
    assert any(i.get("purpose") == "maskable" for i in m["icons"]) and len(m["shortcuts"]) == 3
    assert client.get("/static/icons/icon-maskable-512.png").status_code == 200
    sw = client.get("/sw.js")
    assert sw.headers["content-type"].startswith("text/javascript") and "/offline" in sw.text
    assert "You're offline" in client.get("/offline").text.replace("&#39;", "'")
    assert "serviceWorker.register('/sw.js')" in client.get("/").text

    assert client.get("/.well-known/assetlinks.json").json() == []  # no app key configured
    monkeypatch.setattr(settings, "android_sha256", "aa:bb, CC:DD")
    links = client.get("/.well-known/assetlinks.json").json()
    assert links[0]["target"] == {"namespace": "android_app", "package_name": "com.inviteall.app", "sha256_cert_fingerprints": ["AA:BB", "CC:DD"]}
