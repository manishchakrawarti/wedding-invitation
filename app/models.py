"""Order database (C1). Money is always stored in paise (integer) to avoid rounding bugs."""
import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    QUEUED = "queued"
    GENERATING = "generating"
    QC_REVIEW = "qc_review"  # waiting for the owner to check the draft
    FAILED = "failed"
    PROOF_SENT = "proof_sent"
    CHANGES_REQUESTED = "changes_requested"
    BALANCE_DUE = "balance_due"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


STATUS_LABELS = {
    OrderStatus.PENDING_PAYMENT: "Awaiting payment",
    OrderStatus.QUEUED: "In queue",
    OrderStatus.GENERATING: "Designing",
    OrderStatus.QC_REVIEW: "Quality check",
    OrderStatus.FAILED: "Needs attention",
    OrderStatus.PROOF_SENT: "Proof ready",
    OrderStatus.CHANGES_REQUESTED: "Changes requested",
    OrderStatus.BALANCE_DUE: "Balance due",
    OrderStatus.DELIVERED: "Delivered",
    OrderStatus.CANCELLED: "Cancelled",
}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PENDING_PAYMENT.value, index=True)

    customer_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(200), default="")

    bride_name: Mapped[str] = mapped_column(String(120))
    groom_name: Mapped[str] = mapped_column(String(120))
    bride_name_local: Mapped[str] = mapped_column(String(120), default="")
    groom_name_local: Mapped[str] = mapped_column(String(120), default="")
    bride_family: Mapped[str] = mapped_column(String(200), default="")
    groom_family: Mapped[str] = mapped_column(String(200), default="")
    wedding_date: Mapped[date] = mapped_column(Date)
    venue_name: Mapped[str] = mapped_column(String(200))
    venue_address: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(120), default="")

    language: Mapped[str] = mapped_column(String(8), default="en")
    style: Mapped[str] = mapped_column(String(40))
    package: Mapped[str] = mapped_column(String(20))
    addons: Mapped[list] = mapped_column(JSON, default=list)
    # [{"key": "haldi", "date": "2026-12-10", "time": "10:00", "venue": "..."}]
    functions: Mapped[list] = mapped_column(JSON, default=list)
    customer_notes: Mapped[str] = mapped_column(Text, default="")
    admin_notes: Mapped[str] = mapped_column(Text, default="")

    photo_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)

    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by_code: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(40), default="website")  # website | whatsapp | partner

    payment_option: Mapped[str] = mapped_column(String(10), default="full")  # full | advance
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    amount_paid: Mapped[int] = mapped_column(Integer, default=0)

    current_version: Mapped[int] = mapped_column(Integer, default=0)
    revisions_used: Mapped[int] = mapped_column(Integer, default=0)
    extra_revisions: Mapped[int] = mapped_column(Integer, default=0)
    rsvp_slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assets: Mapped[list["Asset"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    revisions: Mapped[list["Revision"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.id"
    )
    costs: Mapped[list["CostEntry"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    guests: Mapped[list["Guest"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    invitees: Mapped[list["Invitee"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="Invitee.id"
    )
    event: Mapped["EventDetails | None"] = relationship(back_populates="order", cascade="all, delete-orphan", uselist=False)

    @property
    def status_enum(self) -> OrderStatus:
        return OrderStatus(self.status)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status_enum]

    @property
    def balance_due(self) -> int:
        return max(self.total - self.amount_paid, 0)

    @property
    def revisions_left(self) -> int:
        from app.config import settings

        return max(settings.max_free_revisions + self.extra_revisions - self.revisions_used, 0)

    @property
    def api_cost_inr(self) -> float:
        return round(sum(c.cost_inr for c in self.costs), 2)

    def live_assets(self, kind: str, version: int | None = None) -> list["Asset"]:
        version = self.current_version if version is None else version
        return [
            a
            for a in self.assets
            if a.kind == kind and a.deleted_at is None and (kind in ("photo", "video", "music") or a.version == version)
        ]


class Asset(Base):
    """Any stored file: customer photo, AI background, proof (watermarked), final, or manual upload."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # photo | background | proof | final | video
    card_key: Mapped[str] = mapped_column(String(40), default="main")
    version: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(400))
    content_type: Mapped[str] = mapped_column(String(60), default="image/png")
    qc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    order: Mapped[Order] = relationship(back_populates="assets")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))  # full | advance | balance | revision
    amount: Mapped[int] = mapped_column(Integer)  # paise
    provider: Mapped[str] = mapped_column(String(20))  # razorpay | mock | offline
    provider_order_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    provider_payment_id: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="created")  # created | paid | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    order: Mapped[Order] = relationship(back_populates="payments")


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="revisions")


class OrderEvent(Base):
    """Timeline + monitoring log for each order."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info | warn | error
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="events")


class CostEntry(Base):
    __tablename__ = "cost_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    service: Mapped[str] = mapped_column(String(40))
    units: Mapped[float] = mapped_column(Float, default=1)
    cost_inr: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="costs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20))  # whatsapp | email
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # sent | logged | failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Guest(Base):
    """An RSVP response on the event page (B6)."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), default="")
    attending: Mapped[str] = mapped_column(String(10))  # yes | no | maybe
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    functions: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="guests")


class EventDetails(Base):
    """Extras the family adds for the invite experience page."""

    __tablename__ = "event_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    hosts: Mapped[str] = mapped_column(String(200), default="")  # "The Kapoor & Verma families"
    blessing_line: Mapped[str] = mapped_column(String(300), default="")  # "With the blessings of Late Smt. ..."
    story: Mapped[str] = mapped_column(Text, default="")
    hashtag: Mapped[str] = mapped_column(String(60), default="")
    dress_codes: Mapped[dict] = mapped_column(JSON, default=dict)  # function key -> "Yellow / pastel ethnic"
    upi_id: Mapped[str] = mapped_column(String(100), default="")  # shagun
    livestream_url: Mapped[str] = mapped_column(String(300), default="")

    order: Mapped[Order] = relationship(back_populates="event")


class Invitee(Base):
    """One guest (or family) on the couple's guest list, with a personal invite link."""

    __tablename__ = "invitees"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))  # "Sharma Family" or "Meena Aunty"
    phone: Mapped[str] = mapped_column(String(20), default="")
    side: Mapped[str] = mapped_column(String(10), default="")  # bride | groom
    functions: Mapped[list] = mapped_column(JSON, default=list)  # invited to; empty = all
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attending: Mapped[str] = mapped_column(String(10), default="")  # yes | no | maybe | "" (no reply)
    headcount: Mapped[int] = mapped_column(Integer, default=0)
    attending_functions: Mapped[list] = mapped_column(JSON, default=list)
    food: Mapped[str] = mapped_column(String(20), default="")  # veg | jain | non-veg | no-onion-garlic
    arrival_date: Mapped[str] = mapped_column(String(20), default="")
    arrival_mode: Mapped[str] = mapped_column(String(20), default="")  # train | flight | road
    needs_pickup: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, default="")

    order: Mapped[Order] = relationship(back_populates="invitees")
