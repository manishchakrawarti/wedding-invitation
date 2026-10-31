"""Automatic quality checks (C9). Results are stored on each asset; any `fail` keeps the
order in manual review, `warn` is shown to the owner but does not block."""
from PIL import Image, ImageStat

from app.services.cards import CardSpec, expected_texts
from app.services.overlay import CANVAS, OverlayReport, contrast_ratio

try:  # optional: pip install opencv-python-headless
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _faces(img: Image.Image) -> int:
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return len(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)))


def run_qc(card: CardSpec, final: Image.Image, report: OverlayReport, style, used_photo: bool) -> dict:
    checks = []

    expected = [t for t in expected_texts(card)]
    missing = [t for t in expected if not t.strip()]
    if missing or report.rendered != expected:
        checks.append(_check("text_match", "fail", "Rendered text does not match the order details."))
    else:
        checks.append(_check("text_match", "pass", f"{len(expected)} text lines match the order exactly."))

    if report.overflow:
        checks.append(_check("text_fit", "fail", "Text does not fit inside the card — shorten venue or names."))
    elif not report.min_size_ok:
        checks.append(_check("text_fit", "warn", "Some text was shrunk a lot to fit; check it is readable."))
    else:
        checks.append(_check("text_fit", "pass", f"All text fits (scale {report.scale:.2f})."))

    if report.shaping_ok:
        checks.append(_check("script_shaping", "pass", f"Scripts: {', '.join(report.scripts)}."))
    else:
        checks.append(
            _check(
                "script_shaping",
                "fail",
                "Indian-script text needs libraqm + FriBiDi for correct matras/conjuncts. Run in Docker or install FriBiDi.",
            )
        )

    region = final.crop(report.text_bbox) if report.text_bbox[2] > report.text_bbox[0] else final
    avg = tuple(int(c) for c in ImageStat.Stat(region.convert("RGB")).mean)
    ratio = contrast_ratio(style.text_secondary, avg)
    status = "pass" if ratio >= 4.5 else "warn" if ratio >= 3 else "fail"
    checks.append(_check("contrast", status, f"Text contrast {ratio:.1f}:1 against the background."))

    if final.size == CANVAS:
        checks.append(_check("resolution", "pass", f"{final.size[0]}×{final.size[1]} px."))
    else:
        checks.append(_check("resolution", "fail", f"Unexpected size {final.size}."))

    if used_photo and cv2 is not None:
        n = _faces(final)
        checks.append(_check("faces", "pass" if n >= 1 else "warn", f"{n} face(s) detected in the design."))
    elif used_photo:
        checks.append(_check("faces", "skip", "Install opencv-python-headless to enable face detection."))

    return {"passed": all(c["status"] != "fail" for c in checks), "checks": checks}
