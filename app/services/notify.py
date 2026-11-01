"""Customer and owner notifications over Telegram, email and (optionally) the WhatsApp Cloud API (B5).

Telegram (services/telegram.py) and Gmail SMTP are free; Meta charges for WhatsApp Cloud API
messages the business starts, so that channel stays off unless its keys are set.
Without credentials, messages are only written to the Notification log (visible in
the admin panel), so you can test every flow locally.

Note: WhatsApp only allows free-form text within 24 hours of the customer's last
message. For messages outside that window, create approved templates in Meta
Business Manager and switch `_send_whatsapp` to template messages.
"""
import logging
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, Order, TelegramChat
from app.services import telegram
from app.utils import inr, normalize_phone

log = logging.getLogger(__name__)


def order_url(order: Order, path: str = "") -> str:
    return f"{settings.base_url}/o/{order.token}{path}"


def _send_whatsapp(to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body, "preview_url": True}},
        timeout=20,
    )
    resp.raise_for_status()


def _send_email(to: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    for filename, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send(db: Session, channel: str, recipient: str, body: str, subject: str = "", order: Order | None = None,
         attachments: list[tuple[str, bytes, str]] | None = None) -> Notification:
    note = Notification(order_id=order.id if order else None, channel=channel, recipient=recipient, subject=subject, body=body)
    enabled = {"whatsapp": settings.whatsapp_enabled, "telegram": settings.telegram_enabled}.get(channel, settings.email_enabled)
    try:
        if not recipient:
            note.status = "skipped"
        elif not enabled:
            note.status = "logged"
        elif channel == "whatsapp":
            _send_whatsapp(normalize_phone(recipient), body)
            note.status = "sent"
        elif channel == "telegram":
            telegram.send(recipient, body, attachments)
            note.status = "sent"
        else:
            _send_email(recipient, subject or settings.brand_name, body, attachments)
            note.status = "sent"
    except Exception as exc:  # noqa: BLE001 — never let a notification break the order flow
        log.exception("notification failed")
        note.status, note.error = "failed", str(exc)[:500]
    db.add(note)
    db.commit()
    return note


def _messages(order: Order, kind: str) -> tuple[str, str]:
    b = settings.brand_name
    names = order.display_names
    if kind == "order_received":
        return (
            f"Order {order.public_id} received",
            f"Namaste {order.customer_name}! Thank you for choosing {b} for {names}'s invitation 🙏\n"
            f"Order: {order.public_id}\nTrack it any time: {order_url(order)}",
        )
    if kind == "payment_received":
        return (
            f"Payment received for {order.public_id}",
            f"We've received your payment ({inr(order.amount_paid)} so far). Our design studio has started on "
            f"{names}'s invitation. We'll send you a proof soon.\n{order_url(order)}",
        )
    if kind == "proof_ready":
        return (
            f"Your invitation proof is ready — {order.public_id}",
            f"Your invitation proof for {names} is ready! ✨\nPlease review and approve it, or ask for changes "
            f"({order.revisions_left} free revision(s) left):\n{order_url(order, '/proof')}",
        )
    if kind == "balance_due":
        return (
            f"Balance payment for {order.public_id}",
            f"Thank you for approving the design! Please pay the balance of {inr(order.balance_due)} "
            f"to download your final invitation:\n{order_url(order, '/pay?purpose=balance')}",
        )
    if kind == "delivered":
        rsvp = f"\nRSVP page for guests: {settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug else ""
        return (
            f"Your invitation is ready — {order.public_id}",
            f"{'Shubh Vivah! 🎉' if order.is_wedding else '🎉'} Your final invitation for {names} is ready to download and share:\n"
            f"{order_url(order)}{rsvp}\n\nLoved it? Share your referral code {order.referral_code} — friends get "
            f"₹{settings.referral_discount_inr} off.",
        )
    if kind == "video_ready":
        return (f"Your video invite is ready — {order.public_id}", f"Your animated video invitation is ready: {order_url(order)}")
    raise ValueError(kind)


def telegram_chats(db: Session, role: str, order: Order | None = None) -> list[str]:
    stmt = select(TelegramChat.chat_id).where(TelegramChat.role == role)
    if order is not None:
        stmt = stmt.where(TelegramChat.order_id == order.id)
    return list(dict.fromkeys(db.scalars(stmt)))


def notify_customer(db: Session, order: Order, kind: str) -> None:
    subject, body = _messages(order, kind)
    send(db, "whatsapp", order.phone, body, order=order)
    if order.email:
        send(db, "email", order.email, body, subject=f"{settings.brand_name}: {subject}", order=order)
    for chat in telegram_chats(db, "order", order):
        if kind == "delivered":  # the message comes with their e-invite PDF
            from app.services import pipeline

            pipeline.run_background(telegram_order_files, order.id, chat)
        else:
            send(db, "telegram", chat, body, order=order)


def alert_owner(db: Session, message: str, order: Order | None = None) -> None:
    text = f"[{settings.brand_name}] {message}"
    if order:
        text += f"\n{settings.base_url}/admin/orders/{order.id}"
    send(db, "whatsapp", settings.owner_whatsapp, text, order=order)
    send(db, "email", settings.owner_email, text, subject=f"{settings.brand_name} alert", order=order)
    owners = telegram_chats(db, "owner") + [c.strip() for c in settings.telegram_owner_chat_id.split(",") if c.strip()]
    for chat in dict.fromkeys(owners):
        send(db, "telegram", chat, text, order=order)


# --- Telegram: files sent when someone opens the bot, on a worker thread (a PDF takes seconds) --------

def telegram_order_files(order_id: int, chat_id: str) -> None:
    """The customer's e-invite PDF (Full HD if bought, else the free size while previewing) with their links."""
    from app.db import SessionLocal
    from app.models import OrderStatus
    from app.services import export, hires, orders

    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if order is None:
            return
        delivered = order.status == OrderStatus.DELIVERED.value
        if not (delivered or orders.preview_unlockable(order)):
            send(db, "telegram", chat_id, f"🙏 Namaste! You'll get updates for {order.display_names}'s invitation here, "
                                          f"and the PDF as soon as it's ready.\n{order_url(order)}", order=order)
            return
        page = f"\nInvite page for guests: {settings.base_url}/e/{order.rsvp_slug}" if order.rsvp_slug and delivered else ""
        text = (f"💌 Your invitation for {order.display_names}" + (" is ready!" if delivered else " (free preview size)")
                + f"\nDownload, send personal invites and more: {order_url(order)}{page}")
        if not delivered:
            text += f"\nUnlock Full HD and your guest invite page: {order_url(order, '/preview#unlock')}"
        _send_pdf(db, order, chat_id, text, lambda: export.render(order, "pdf", "1080" if delivered and hires.allowed(order, "1080") else "free"),
                  f"{order.display_names} invitation.pdf")


def telegram_invitee_files(code: str, chat_id: str) -> None:
    """A guest's personal invitation PDF, with their own link."""
    from app.db import SessionLocal
    from app.models import Invitee
    from app.services import export, hires, invites

    with SessionLocal() as db:
        invitee = db.scalar(select(Invitee).where(Invitee.code == code))
        if invitee is None:
            return
        order = invitee.order
        sender = invites.sender_line(invitee)
        text = f"💌 {invitee.name}, your invitation: {order.display_names}\n{invites.invite_url(invitee)}" + (f"\n{sender}" if sender else "")
        if not invites.can_send(order):
            send(db, "telegram", chat_id, text, order=order)
            return
        tier = "1080" if hires.allowed(order, "1080") else "free"
        _send_pdf(db, order, chat_id, text, lambda: export.render(order, "pdf", tier, invitee=invitee),
                  f"{order.display_names} invitation for {invitee.name}.pdf")


def _send_pdf(db: Session, order: Order, chat_id: str, text: str, make_pdf, filename: str) -> None:
    from app.services import export

    try:
        pdf = make_pdf()
    except export.ExportUnavailable:
        send(db, "telegram", chat_id, text, order=order)  # the links still work without the file
        return
    send(db, "telegram", chat_id, text, order=order, attachments=[(filename.replace("/", "-"), pdf, "application/pdf")])
