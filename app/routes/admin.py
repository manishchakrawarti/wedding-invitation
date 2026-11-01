"""Admin & operations (D1 dashboard, D2 revision tracker, D4 revenue export, D5 cost tracker)."""
import csv
import io
import secrets
from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalog import FUNCTIONS, LANGUAGES, PACKAGES, STYLES
from app.config import settings
from app.db import get_db
from app.models import Asset, Notification, Order, OrderStatus, Payment, TelegramChat
from app.services import notify, orders, payments, pipeline
from app.services.maintenance import cleanup_expired
from app.services.storage import storage
from app.templating import templates

security = HTTPBasic()


def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(creds.username.encode(), settings.admin_username.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), settings.admin_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": 'Basic realm="admin"'})
    return creds.username


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def back(order: Order, msg: str = "") -> RedirectResponse:
    return RedirectResponse(f"/admin/orders/{order.id}" + (f"?msg={msg}" if msg else ""), status_code=303)


def load(order_id: int, db: Session) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404)
    return order


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, status: str = "", q: str = "", msg: str = "", db: Session = Depends(get_db)):
    all_orders = db.scalars(select(Order).order_by(Order.created_at.desc())).all()
    stmt = select(Order).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Order.public_id.ilike(like), Order.bride_name.ilike(like), Order.groom_name.ilike(like), Order.phone.ilike(like), Order.customer_name.ilike(like)))
    rows = db.scalars(stmt.limit(300)).all()

    to_confirm = [o for o in all_orders if any(p.status == "claimed" for p in o.payments)]
    paid = [o for o in all_orders if o.amount_paid > 0 and o.source not in ("test", "demo")]
    revenue = sum(o.amount_paid for o in paid)
    cost = sum(o.api_cost_inr for o in all_orders if o.source not in ("test", "demo")) * 100
    month = date.today().replace(day=1)
    by_month: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # wedding month -> [orders, revenue]
    for o in paid:
        key = o.wedding_date.strftime("%Y-%m")
        by_month[key][0] += 1
        by_month[key][1] += o.amount_paid
    stats = {
        "orders": len(paid),
        "revenue": revenue,
        "cost": cost,
        "margin": revenue - cost,
        "avg_cost": (cost / len(paid)) if paid else 0,
        "this_month": sum(1 for o in paid if o.created_at.date() >= month),
        "status_counts": Counter(o.status for o in all_orders),
        "by_month": sorted(by_month.items())[-12:],
        "max_month": max((v[1] for v in by_month.values()), default=0) or 1,
        "packages": Counter(o.package for o in paid),
        "occasions": Counter(o.occasion_name for o in paid),
    }
    tg_owners = db.scalars(select(TelegramChat).where(TelegramChat.role == "owner")).all()
    return templates.TemplateResponse(request, "admin/dashboard.html", {"rows": rows, "stats": stats, "status": status, "q": q, "msg": msg,
                                                                        "to_confirm": to_confirm, "tg_owners": tg_owners})


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(request: Request, order_id: int, msg: str = "", db: Session = Depends(get_db)):
    order = load(order_id, db)
    versions = sorted({a.version for a in order.assets if a.kind == "proof"}, reverse=True)
    notes = db.scalars(select(Notification).where(Notification.order_id == order.id).order_by(Notification.id.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/order.html",
        {
            "o": order, "msg": msg, "versions": versions, "notes": notes, "styles": STYLES, "languages": LANGUAGES,
            "functions": FUNCTIONS, "packages": PACKAGES,
            "finals": order.live_assets("final"), "photos": order.live_assets("photo"), "videos": order.live_assets("video"),
            "last_revision": order.revisions[-1].notes if order.revisions else "",
        },
    )


@router.get("/assets/{asset_id}")
def asset_file(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None or asset.deleted_at:
        raise HTTPException(404)
    return Response(storage.read(asset.path), media_type=asset.content_type)


@router.post("/orders/{order_id}/regenerate")
async def regenerate(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    form = await request.form()
    if order.status in (OrderStatus.PENDING_PAYMENT.value, OrderStatus.CANCELLED.value, OrderStatus.DELIVERED.value):
        return back(order, "Order must be paid and not delivered/cancelled to regenerate.")
    orders.set_status(db, order, OrderStatus.QUEUED, "Regeneration requested by admin")
    db.commit()
    pipeline.enqueue(order.id, str(form.get("notes", "")))
    return back(order, "Regeneration started — refresh in a minute.")


@router.post("/orders/{order_id}/send-proof")
def send_proof(order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    if not order.live_assets("proof"):
        return back(order, "No proof generated yet.")
    orders.send_proof(db, order)
    return back(order, "Proof sent to customer.")


@router.post("/orders/{order_id}/deliver")
def deliver(order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    if not order.live_assets("final"):
        return back(order, "No final files yet.")
    orders.deliver(db, order)
    return back(order, "Delivered and customer notified.")


@router.post("/orders/{order_id}/edit")
async def edit(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    form = await request.form()
    for field in ("bride_name", "groom_name", "bride_name_local", "groom_name_local", "bride_family", "groom_family",
                  "venue_name", "venue_address", "city", "admin_notes"):
        if field in form:
            setattr(order, field, str(form[field]).strip())
    if form.get("style") in STYLES:
        order.style = str(form["style"])
    if form.get("language") in LANGUAGES:
        order.language = str(form["language"])
    try:
        order.wedding_date = date.fromisoformat(str(form.get("wedding_date")))
    except ValueError:
        pass
    orders.log_event(db, order, "Order details edited by admin")
    db.commit()
    return back(order, "Saved. Regenerate to apply changes to the design.")


@router.post("/orders/{order_id}/grant-revision")
def grant_revision(order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    order.extra_revisions += 1
    orders.log_event(db, order, "Admin granted one extra free revision")
    db.commit()
    return back(order, "Extra revision granted.")


@router.post("/orders/{order_id}/offline-payment")
async def offline_payment(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    form = await request.form()
    try:
        amount = int(form.get("amount") or 0)
    except ValueError:
        amount = 0
    if amount <= 0:
        return back(order, "Enter an amount in rupees.")
    payments.record_offline_payment(db, order, amount, str(form.get("note", "")).strip())
    return back(order, f"Recorded ₹{amount} payment.")


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(payment_id: int, db: Session = Depends(get_db)):
    """Owner checked the Razorpay dashboard and the money arrived."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404)
    order = payment.order
    payments.mark_paid(db, payment, payment.provider_payment_id or "confirmed-by-admin")
    return back(order, f"Payment of ₹{payment.amount // 100} confirmed.")


@router.post("/orders/{order_id}/upload")
async def upload(request: Request, order_id: int, db: Session = Depends(get_db)):
    """Upload a hand-made file (e.g. the video invite) as part of the delivery."""
    order = load(order_id, db)
    form = await request.form()
    file = form.get("file")
    kind = "video" if form.get("kind") == "video" else "final"
    if not getattr(file, "filename", ""):
        return back(order, "Choose a file.")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    types = {"mp4": "video/mp4", "mov": "video/quicktime", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf"}
    if ext not in types:
        return back(order, "Allowed: mp4, mov, png, jpg, pdf.")
    card_key = str(form.get("card_key") or kind).strip() or kind
    key = storage.save(f"orders/{order.public_id}/manual/{secrets.token_hex(4)}_{card_key}.{ext}", await file.read())
    db.add(Asset(order_id=order.id, kind=kind, card_key=card_key, version=order.current_version, path=key, content_type=types[ext], meta={"title": card_key}))
    orders.log_event(db, order, f"Admin uploaded {kind}: {file.filename}")
    db.commit()
    if kind == "video" and order.status == OrderStatus.DELIVERED.value:
        notify.notify_customer(db, order, "video_ready")
    return back(order, "Uploaded.")


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: int, db: Session = Depends(get_db)):
    order = load(order_id, db)
    orders.set_status(db, order, OrderStatus.CANCELLED, "Cancelled by admin")
    db.commit()
    return back(order, "Order cancelled. Process any refund in the Razorpay dashboard.")


RESEND_KIND = {
    OrderStatus.PENDING_PAYMENT.value: "order_received",
    OrderStatus.PROOF_SENT.value: "proof_ready",
    OrderStatus.BALANCE_DUE.value: "balance_due",
    OrderStatus.DELIVERED.value: "delivered",
}


@router.post("/orders/{order_id}/resend")
def resend(order_id: int, db: Session = Depends(get_db)):
    """Re-send the message for the order's current stage (e.g. after setting up email)."""
    order = load(order_id, db)
    kind = RESEND_KIND.get(order.status, "payment_received")
    notify.notify_customer(db, order, kind)
    last = db.scalars(select(Notification).where(Notification.order_id == order.id).order_by(Notification.id.desc())).first()
    return back(order, f"Re-sent '{kind}' message — latest status: {last.status if last else 'n/a'}{(' (' + last.error[:120] + ')') if last and last.error else ''}")


@router.get("/notifications", response_class=HTMLResponse)
def notifications(request: Request, msg: str = "", db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).order_by(Notification.id.desc()).limit(200)).all()
    return templates.TemplateResponse(request, "admin/notifications.html", {"rows": rows, "msg": msg})


@router.post("/notifications/test-email")
async def test_email(request: Request, db: Session = Depends(get_db)):
    to = str((await request.form()).get("to", "")).strip()
    note = notify.send(db, "email", to, f"This is a test email from {settings.brand_name}. Email sending works! 🎉",
                       subject=f"{settings.brand_name}: test email")
    result = {"sent": "Sent! Check the inbox (and spam folder).", "logged": "Not sent: SMTP is not configured in .env.",
              "skipped": "Enter an email address."}.get(note.status, f"Failed: {note.error[:200]}")
    return RedirectResponse(f"/admin/notifications?msg={result}", status_code=303)


@router.post("/cleanup")
def run_cleanup(db: Session = Depends(get_db)):
    result = cleanup_expired(db)
    return RedirectResponse(f"/admin?msg=Cleanup removed {result['files_removed']} file(s)", status_code=303)


@router.get("/export/orders.csv")
def export_orders(db: Session = Depends(get_db)):
    """Feed this into Looker Studio / Power BI for the revenue dashboard (D4)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order_id", "created_at", "status", "package", "addons", "style", "language", "wedding_date", "wedding_month",
                "city", "source", "subtotal_inr", "discount_inr", "total_inr", "paid_inr", "api_cost_inr", "margin_inr",
                "revisions_used", "referred_by", "marketing_consent"])
    for o in db.scalars(select(Order).order_by(Order.id)):
        w.writerow([o.public_id, o.created_at.isoformat(timespec="minutes"), o.status, o.package, " ".join(o.addons or []), o.style,
                    o.language, o.wedding_date.isoformat(), o.wedding_date.strftime("%Y-%m"), o.city, o.source,
                    o.subtotal / 100, o.discount / 100, o.total / 100, o.amount_paid / 100, o.api_cost_inr,
                    round(o.amount_paid / 100 - o.api_cost_inr, 2), o.revisions_used, o.referred_by_code, o.marketing_consent])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="orders.csv"'})
