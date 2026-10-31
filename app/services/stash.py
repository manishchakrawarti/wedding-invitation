"""Keeps a form's uploaded photos for a few hours. Browsers always empty file inputs when a page is shown
again, so without this a single validation error (say, the photo-permission box left unticked) silently
loses the bride / groom / family photos and the gift QR the customer had chosen."""
import re
import secrets

from app.services.storage import storage

NAMES = ("bride", "groom", "family", "gift_qr")
MAX_AGE_S = 6 * 3600
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,40}")


def valid(token: str) -> bool:
    return bool(token and _TOKEN.fullmatch(token))


def new_token() -> str:
    return secrets.token_urlsafe(18)


def _key(token: str, name: str) -> str:
    return f"stash/{token}/{name}"


def put(token: str, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if name in NAMES and data:
            storage.save(_key(token, name), data)


def get(token: str, name: str) -> bytes | None:
    if not valid(token) or name not in NAMES or not storage.exists(_key(token, name)):
        return None
    return storage.read(_key(token, name))


def kept(token: str) -> dict[str, bytes]:
    """Every file still kept for this form."""
    found = {name: get(token, name) for name in NAMES} if valid(token) else {}
    return {name: data for name, data in found.items() if data}


def drop(token: str) -> None:
    if valid(token):
        for name in NAMES:
            storage.delete(_key(token, name))


def purge() -> int:
    return storage.purge("stash/", MAX_AGE_S)
