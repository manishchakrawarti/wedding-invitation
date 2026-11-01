"""Free notifications over a Telegram bot: owner alerts, customer updates with their e-invite PDF,
and a guest's personal PDF.

Telegram's Bot API costs nothing, but a bot can only message people who opened it first, so every
chat starts from a link like t.me/<bot>?start=<payload>:

  admin_<signature>   the owner: alerts (new payments to confirm, failed orders…)
  o_<order token>     a customer: status updates and their e-invite PDF
  i_<invitee code>    a guest: their personal invitation PDF

Set TELEGRAM_BOT_TOKEN (from @BotFather) and the webhook is registered on startup.
"""
import hashlib
import hmac
import logging
import threading
import time

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_username: str = ""
_username_checked = 0.0
_recent: dict[tuple[str, str], float] = {}  # (chat, payload) -> when its PDF was last sent
PDF_COOLDOWN_S = 300


def enabled() -> bool:
    return bool(settings.telegram_bot_token)


def _call(method: str, data: dict | None = None, files: dict | None = None, timeout: float = 60) -> dict:
    resp = httpx.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}", data=data, files=files,
                      timeout=timeout)
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method}: {body.get('description', resp.status_code)}")
    return body["result"]


def _sign(text: str) -> str:
    return hmac.new(settings.telegram_bot_token.encode(), text.encode(), hashlib.sha256).hexdigest()[:20]


def webhook_secret() -> str:
    return _sign("webhook")


def owner_payload() -> str:
    return f"admin_{_sign('owner')}"


def bot_username() -> str:
    """The bot's @username for t.me links (from TELEGRAM_BOT_USERNAME, else asked once from Telegram)."""
    global _username, _username_checked
    if settings.telegram_bot_username:
        return settings.telegram_bot_username.lstrip("@")
    if not _username and enabled() and time.time() - _username_checked > 300:
        _username_checked = time.time()
        try:
            _username = _call("getMe", timeout=5)["username"]
        except Exception:  # noqa: BLE001 — links just stay hidden until Telegram answers
            log.warning("Telegram getMe failed", exc_info=True)
    return _username


def link(payload: str) -> str:
    """t.me deep link that opens the bot and sends it /start <payload>, or "" if Telegram is off."""
    name = bot_username() if enabled() else ""
    return f"https://t.me/{name}?start={payload}" if name else ""


def order_link(order) -> str:
    return link(f"o_{order.token}")


def invitee_link(invitee) -> str:
    return link(f"i_{invitee.code}")


def owner_link() -> str:
    return link(owner_payload())


def send(chat_id: str, text: str, attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    """A message, or a document per attachment with the text as the first one's caption."""
    if not attachments:
        _call("sendMessage", {"chat_id": chat_id, "text": text[:4096]})
        return
    for i, (filename, data, mime) in enumerate(attachments):
        caption = text[:1024] if i == 0 else ""
        _call("sendDocument", {"chat_id": chat_id, "caption": caption}, files={"document": (filename, data, mime)}, timeout=120)
    if len(text) > 1024:
        _call("sendMessage", {"chat_id": chat_id, "text": text[:4096]})


def pdf_allowed(chat_id: str, payload: str) -> bool:
    """Rendering a PDF is the heaviest thing the server does: one per chat and link every few minutes."""
    now = time.time()
    if now - _recent.get((chat_id, payload), 0) < PDF_COOLDOWN_S:
        return False
    _recent[(chat_id, payload)] = now
    return True


def setup() -> None:
    """Point the bot's webhook at this site (safe to repeat). Runs on a thread at startup."""
    def run():
        try:
            _call("setWebhook", {"url": f"{settings.base_url}/webhooks/telegram", "secret_token": webhook_secret(),
                                 "allowed_updates": '["message"]', "drop_pending_updates": "true"}, timeout=20)
            log.info("Telegram webhook set for @%s", bot_username())
        except Exception:  # noqa: BLE001
            log.warning("Telegram webhook setup failed", exc_info=True)

    threading.Thread(target=run, name="telegram-setup", daemon=True).start()
