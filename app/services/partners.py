"""Partner programme: vendors (mehndi artists, pandits, photographers, halls, printers) share their own link;
families who come through it are tagged on their order, and the partner earns a share of what they pay."""
import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, Partner

COOKIE = "ia_partner"
BUSINESSES = {
    "mehndi": "Mehndi artist", "pandit": "Pandit / priest", "photographer": "Photographer", "venue": "Banquet hall / venue",
    "decorator": "Decorator / caterer", "printer": "Card printer", "planner": "Wedding planner", "other": "Other",
}


def new_code(db: Session, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]", "", name.upper())[:8] or "PARTNER"
    while True:
        code = f"{base}{secrets.randbelow(900) + 100}"
        if not db.scalar(select(Partner).where(Partner.code == code)):
            return code


def by_code(db: Session, code: str) -> Partner | None:
    code = (code or "").strip().upper()[:24]
    if not code:
        return None
    return db.scalar(select(Partner).where(Partner.code == code, Partner.active.is_not(False)))


def link(partner: Partner) -> str:
    return f"{settings.base_url}/p/{partner.code}"


def share_text(partner: Partner) -> str:
    return (f"🙏 Make your wedding, puja or birthday invitation free in 2 minutes: card, video, PDF and a personal "
            f"WhatsApp invite for every guest, in Hindi and 9 Indian languages.\n{link(partner)}")


def summary(db: Session, partner: Partner) -> dict:
    """Families referred, how many paid, what they paid, and what the partner has earned and is owed (paise)."""
    made, paid, revenue = db.execute(
        select(func.count(Order.id), func.count(Order.id).filter(Order.amount_paid > 0),
               func.coalesce(func.sum(Order.amount_paid), 0)).where(Order.partner_code == partner.code)).one()
    earned = revenue * settings.partner_commission_percent // 100
    return {"made": made, "paid": paid, "revenue": revenue, "earned": earned, "owed": max(earned - (partner.paid_out or 0), 0)}
