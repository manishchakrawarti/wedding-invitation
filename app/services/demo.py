"""A ready-made sample wedding for the website's "See a live demo" button and for sharing on Instagram."""
import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import EventDetails, Invitee, Order, OrderStatus, utcnow
from app.services import invites, orders, pipeline
from app.utils import new_token

log = logging.getLogger(__name__)

GUESTS = [
    # name, side, functions, attending, headcount, food, message
    ("Sharma Family", "bride", [], "", 0, "", ""),
    ("Meena Bua & Family", "bride", ["haldi", "mehndi", "wedding"], "yes", 4, "veg", "Bahut bahut badhaai! Can't wait to dance at the sangeet 💃"),
    ("Rahul & Sneha", "groom", ["sangeet", "wedding", "reception"], "yes", 2, "jain", "So happy for you both! Wishing you a lifetime of laughter ❤️"),
    ("Verma Uncle", "groom", ["wedding", "reception"], "maybe", 3, "veg", ""),
    ("Dr. Iyer", "groom", ["reception"], "no", 0, "", "Blessings from Chennai. Sorry we can't travel — sending lots of love 🙏"),
]


def demo_order() -> Order | None:
    with SessionLocal() as db:
        return db.scalar(select(Order).where(Order.source == "demo"))


def ensure_demo() -> None:
    """Create the demo wedding once, with real generated cards."""
    if demo_order():
        return
    day = date.today() + timedelta(days=60)
    iso = lambda d: d.isoformat()  # noqa: E731
    with SessionLocal() as db:
        order = Order(
            public_id=orders.new_public_id(db), token=new_token(), status=OrderStatus.QUEUED.value, source="demo",
            customer_name="Demo", phone="910000000000", bride_name="Ananya", groom_name="Arjun",
            bride_family="Mrs & Mr Rakesh Sharma", groom_family="Mrs & Mr Vikram Mehta",
            wedding_date=day, venue_name="The Royal Palace Gardens", venue_address="Amer Road", city="Jaipur",
            language="en", style="north_indian", package="premium", addons=[],
            functions=[
                {"key": "haldi", "date": iso(day - timedelta(days=2)), "time": "10:00", "venue": "Sharma Haveli"},
                {"key": "mehndi", "date": iso(day - timedelta(days=2)), "time": "16:00", "venue": "Sharma Haveli"},
                {"key": "sangeet", "date": iso(day - timedelta(days=1)), "time": "19:30", "venue": ""},
                {"key": "wedding", "date": iso(day), "time": "19:30", "venue": ""},
                {"key": "reception", "date": iso(day + timedelta(days=1)), "time": "20:00", "venue": "Rambagh Palace"},
            ],
            referral_code=orders.new_referral_code(db, "demo"), total=0, amount_paid=0,
        )
        db.add(order)
        db.flush()
        db.add(EventDetails(
            order_id=order.id, hosts="The Sharma & Mehta families", hashtag="#AnanyaKaArjun",
            blessing_line="With the blessings of Late Smt. Kamla Devi Sharma",
            story="We met in a Jaipur bookshop, both reaching for the last copy of the same novel.\n"
                  "Arjun let Ananya have it — on the condition that she'd tell him the ending over chai.\n"
                  "Five years and countless cups of chai later, we're writing our own story. Come celebrate it with us!",
            dress_codes={"haldi": "Yellow ethnic 💛", "mehndi": "Green & bright colours", "sangeet": "Indo-western glam ✨",
                         "wedding": "Traditional ethnic", "reception": "Formal: gowns & suits"},
            upi_id="demo@upi",
        ))
        for name, side, fns, attending, count, food, message in GUESTS:
            db.add(Invitee(
                order_id=order.id, code=invites.new_code(db), name=name, side=side, functions=fns,
                attending=attending, headcount=count, attending_functions=fns if attending in ("yes", "maybe") else [],
                food=food, message=message, sent_at=utcnow(), opened_at=utcnow() if attending else None,
                open_count=2 if attending else 0, responded_at=utcnow() if attending else None,
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
    log.info("demo wedding created")
