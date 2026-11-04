"""Video invitations: the e-invite's pages (cover with Ganesha, invitation, cards, schedule, venue, closing) as a
9:16 video for WhatsApp status and Instagram stories. Each page slowly zooms over a soft blurred copy of itself,
pages crossfade, and the family's own music plays (or an original tune from services/music.py).
Included with the 2K and 4K downloads."""
import hashlib
import io
import logging
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image

from app.config import settings
from app.models import Asset, Order
from app.services import export, hires, music
from app.services.overlay import CANVAS
from app.services.storage import storage

log = logging.getLogger(__name__)

W, H = 720, 1280  # 9:16
CARD_W, CARD_H = 640, 800  # each page, centred
FPS = 25
PAGE_SECONDS = 4.0
FADE = 0.8
MAX_PAGES = 9
TIER = "1080"  # page images without the free credit
_making: set[int] = set()
_lock = threading.Lock()


def allowed(order: Order) -> bool:
    return hires.allowed(order, "2k")


def latest(order: Order) -> Asset | None:
    videos = [a for a in order.live_assets("video") if a.card_key == "auto"]
    return max(videos, key=lambda a: a.id) if videos else None


def state(order: Order) -> str:
    """ready | stale (details changed since) | making | none"""
    if order.id in _making:
        return "making"
    v = latest(order)
    if v is None:
        return "none"
    return "stale" if order.updated_at and v.created_at and order.updated_at > v.created_at else "ready"


def _pages(order: Order) -> list[Image.Image]:
    # export._render, not export.render: build() already holds the one-heavy-render-at-a-time lock
    long_img = Image.open(io.BytesIO(export._render(order, "image", TIER))).convert("RGB")
    page_h = round(long_img.width * CANVAS[1] / CANVAS[0])
    count = max(1, round(long_img.height / page_h))
    pages = [long_img.crop((0, i * page_h, long_img.width, (i + 1) * page_h)) for i in range(count)]
    if len(pages) > MAX_PAGES:  # keep the cover, the invitation, the first cards and the closing page
        pages = pages[: MAX_PAGES - 1] + pages[-1:]
    return pages


def _music_file(order: Order, folder: Path) -> Path:
    uploaded = next(iter(sorted(order.live_assets("music"), key=lambda a: a.id, reverse=True)), None)
    if uploaded:
        path = folder / ("music." + uploaded.path.rsplit(".", 1)[-1])
        path.write_bytes(storage.read(uploaded.path))
        return path
    path = folder / "music.wav"
    path.write_bytes(music.background_wav())
    return path


def encode(pages: list[Image.Image], music_path: Path, folder: Path) -> bytes:
    """ffmpeg: zoom each page over its blurred copy, crossfade, add music."""
    import imageio_ffmpeg

    n = len(pages)
    total = n * PAGE_SECONDS - (n - 1) * FADE
    inputs, filters = [], []
    for i, page in enumerate(pages):
        path = folder / f"p{i}.png"
        page.resize((CARD_W * 2, CARD_H * 2), Image.LANCZOS).save(path)
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{PAGE_SECONDS}", "-i", str(path)]
        frames = int(PAGE_SECONDS * FPS)
        zoom = f"1+0.06*in/{frames}"  # gentle push-in over the page's time
        filters.append(
            f"[{i}:v]split=2[a{i}][b{i}];"
            f"[a{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=26:2,eq=brightness=-0.18[bg{i}];"
            f"[b{i}]zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={CARD_W}x{CARD_H}:fps={FPS}[fg{i}];"
            f"[bg{i}][fg{i}]overlay={(W - CARD_W) // 2}:{(H - CARD_H) // 2},format=yuv420p,setsar=1[s{i}]"
        )
    chain, last = [], "s0"
    for i in range(1, n):
        offset = i * (PAGE_SECONDS - FADE)
        chain.append(f"[{last}][s{i}]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[x{i}]")
        last = f"x{i}"
    filters += chain
    filters.append(f"[{n}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,afade=t=in:d=1,afade=t=out:st={max(total - 2.5, 0):.2f}:d=2.5[aud]")
    out = folder / "invite.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", *inputs, "-stream_loop", "-1", "-i", str(music_path),
           "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", "[aud]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode(errors='ignore')[-400:]}")
    return out.read_bytes()


def build(order: Order) -> bytes:
    with export._render_slots, tempfile.TemporaryDirectory() as tmp:  # one heavy render at a time
        folder = Path(tmp)
        return encode(_pages(order), _music_file(order, folder), folder)


def make_for_order(order_id: int) -> None:
    """Background job: render and store the order's video, replacing the previous one."""
    from app.db import SessionLocal
    from app.models import utcnow
    from app.services import orders

    try:
        with SessionLocal() as db:
            order = db.get(Order, order_id)
            if order is None:
                return
            data = build(order)
            key = f"orders/{order.public_id}/video_{hashlib.sha1(data).hexdigest()[:12]}.mp4"
            storage.save(key, data)
            for old in [a for a in order.live_assets("video") if a.card_key == "auto"]:
                storage.delete(old.path)
                old.deleted_at = utcnow()
            db.add(Asset(order_id=order.id, kind="video", card_key="auto", path=key, content_type="video/mp4"))
            orders.log_event(db, order, f"Video invitation made ({len(data) // 1024} KB)")
            db.commit()
    except Exception:  # noqa: BLE001 — the page offers to try again
        log.exception("video for order %s failed", order_id)
    finally:
        with _lock:
            _making.discard(order_id)


def start(order: Order) -> None:
    from app.services import pipeline

    with _lock:
        if order.id in _making:
            return
        _making.add(order.id)
    pipeline.run_background(make_for_order, order.id)


SAMPLE = settings.data_dir / "samples" / "video_sample.mp4"


def ensure_sample() -> None:
    """The sample video shown to customers before they upgrade: made once from the English wedding demo."""
    from app.services import demo
    from app.services.overlay import CARD_DESIGN

    target = SAMPLE.with_name(f"video_sample_d{CARD_DESIGN}.mp4")
    if target.exists():
        return
    order = demo.demo_order("en")
    if order is None:
        return
    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            data = build(db.get(Order, order.id))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        log.info("sample video made (%d KB)", len(data) // 1024)
    except Exception:  # noqa: BLE001
        log.exception("sample video failed")


def sample_path() -> Path | None:
    from app.services.overlay import CARD_DESIGN

    target = SAMPLE.with_name(f"video_sample_d{CARD_DESIGN}.mp4")
    return target if target.exists() else None
