"""Inbound webhooks: Razorpay payment confirmations and WhatsApp auto-replies (E2)."""
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import PACKAGES
from app.config import settings
from app.db import get_db
from app.models import Order
from app.services import notify, payments

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")


@router.post("/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not payments.verify_webhook_signature(body, request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(400, "bad signature")
    event = json.loads(body)
    if event.get("event") in ("payment.captured", "order.paid"):
        entity = event["payload"]["payment"]["entity"]
        payment = payments.find_by_provider_order(db, entity.get("order_id", ""))
        if payment:
            payments.mark_paid(db, payment, entity["id"])
    return {"ok": True}


@router.get("/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == settings.whatsapp_verify_token:
        return q.get("hub.challenge", "")
    raise HTTPException(403)


def price_list() -> str:
    lines = [f"*{p.name}* — ₹{p.price:,}: {p.tagline}" for p in PACKAGES.values()]
    return "\n".join(lines)


def auto_reply(db: Session, text: str) -> str:
    order_id = re.search(rf"{settings.order_prefix}-\d{{4}}-[A-Z0-9]{{4}}", text.upper())
    if order_id:
        order = db.scalar(select(Order).where(Order.public_id == order_id.group(0)))
        if order:
            return f"Order {order.public_id} status: *{order.status_label}*.\nDetails: {notify.order_url(order)}"
    return (
        f"Namaste 🙏 Welcome to *{settings.brand_name}* — {settings.brand_tagline}.\n\n"
        f"{price_list()}\n\n"
        f"See samples & order in 3 minutes: {settings.base_url}/order\n"
        f"Already ordered? Send your order ID (e.g. {settings.order_prefix}-2612-AB12) to get its status."
    )


@router.post("/whatsapp")
async def whatsapp_inbound(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                sender = msg.get("from", "")
                text = msg.get("text", {}).get("body", "") if msg.get("type") == "text" else ""
                if sender:
                    notify.send(db, "whatsapp", sender, auto_reply(db, text))
    return {"ok": True}
