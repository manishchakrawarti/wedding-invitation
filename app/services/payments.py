"""Payments (B3) via Razorpay (UPI, cards, netbanking). Falls back to a "simulate payment"
mode when no Razorpay keys are configured so the flow can be tested end to end."""
import hashlib
import hmac

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, OrderStatus, Payment, utcnow
from app.services import notify, orders, pipeline


def create_payment(db: Session, order: Order, purpose: str) -> Payment:
    amount = orders.amount_for(order, purpose)
    if amount <= 0:
        raise ValueError("Nothing to pay")
    # Reuse an unpaid payment for the same purpose and amount (customer refreshed the page).
    existing = next(
        (p for p in order.payments
         if p.purpose == purpose and p.status in ("created", "claimed") and p.amount == amount and p.provider == settings.payment_provider),
        None,
    )
    if existing:
        return existing

    payment = Payment(order_id=order.id, purpose=purpose, amount=amount, provider=settings.payment_provider)
    db.add(payment)
    db.flush()
    if payment.provider == "razorpay":
        resp = httpx.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={"amount": amount, "currency": "INR", "receipt": f"{order.public_id}-{payment.id}", "notes": {"purpose": purpose}},
            timeout=20,
        )
        resp.raise_for_status()
        payment.provider_order_id = resp.json()["id"]
    else:
        payment.provider_order_id = f"{payment.provider}_{payment.id}"
    db.commit()
    return payment


def claim_manual_payment(db: Session, payment: Payment, reference: str) -> None:
    """Customer says they paid on the Razorpay.me page; the owner confirms it in admin."""
    order = payment.order
    payment.status = "claimed"
    payment.provider_payment_id = reference[:80]
    orders.log_event(db, order, f"Customer reports paying ₹{payment.amount // 100} ({payment.purpose}) via Razorpay.me, ref: {reference}")
    db.commit()
    notify.alert_owner(
        db,
        f"{order.public_id}: customer says they paid ₹{payment.amount // 100} ({payment.purpose}), ref {reference}. "
        "Check your Razorpay dashboard, then confirm it in admin.",
        order,
    )


def verify_checkout_signature(provider_order_id: str, provider_payment_id: str, signature: str) -> bool:
    msg = f"{provider_order_id}|{provider_payment_id}".encode()
    expected = hmac.new(settings.razorpay_key_secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def find_by_provider_order(db: Session, provider_order_id: str) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.provider_order_id == provider_order_id))


def mark_paid(db: Session, payment: Payment, provider_payment_id: str = "") -> None:
    """Idempotent: Razorpay may call the webhook and the browser callback for the same payment."""
    if payment.status == "paid":
        return
    order = payment.order
    payment.status = "paid"
    payment.paid_at = utcnow()
    payment.provider_payment_id = provider_payment_id
    order.amount_paid += payment.amount
    orders.log_event(db, order, f"Payment received: {payment.purpose} ₹{payment.amount // 100} via {payment.provider}")

    if payment.purpose == "revision":
        order.extra_revisions += 1
        db.commit()
        return

    if order.status == OrderStatus.PREVIEW.value and order.balance_due == 0:
        orders.deliver(db, order)
    elif order.status == OrderStatus.PENDING_PAYMENT.value:
        orders.set_status(db, order, OrderStatus.QUEUED, "Paid — queued for design")
        db.commit()
        notify.notify_customer(db, order, "payment_received")
        pipeline.enqueue(order.id)
    elif order.status == OrderStatus.BALANCE_DUE.value and order.balance_due == 0:
        orders.deliver(db, order)
    else:
        db.commit()


def apply_test_coupon(db: Session, order: Order, code: str) -> bool:
    """Owner's test coupon: makes an unlockable instant preview free and delivers it like a paid one."""
    if not (settings.test_coupon_code and hmac.compare_digest(code.strip().upper(), settings.test_coupon_code.upper())):
        return False
    if not orders.preview_unlockable(order):
        return False
    order.discount += order.balance_due
    order.total = order.amount_paid
    orders.log_event(db, order, "Test coupon applied: unlocked for free")
    orders.deliver(db, order)
    return True


def record_offline_payment(db: Session, order: Order, amount_inr: int, note: str) -> None:
    """For UPI/cash/bank transfers received outside Razorpay; entered by the owner."""
    payment = Payment(order_id=order.id, purpose="balance" if order.amount_paid else "full", amount=amount_inr * 100, provider="offline")
    db.add(payment)
    db.flush()
    orders.log_event(db, order, f"Offline payment recorded by admin: {note or 'no note'}")
    mark_paid(db, payment, provider_payment_id=f"offline:{note}"[:80])
