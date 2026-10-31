"""Download the open-source (OFL) fonts used on the invitation cards into app/assets/fonts.

    python scripts/fetch_fonts.py
"""
import sys
import urllib.request
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

FONTS = {
    "GreatVibes-Regular.ttf": "greatvibes/GreatVibes-Regular.ttf",
    "Cinzel.ttf": "cinzel/Cinzel%5Bwght%5D.ttf",
    "CormorantGaramond.ttf": "cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
    "NotoSerifDevanagari.ttf": "notoserifdevanagari/NotoSerifDevanagari%5Bwdth,wght%5D.ttf",
    "NotoSerifBengali.ttf": "notoserifbengali/NotoSerifBengali%5Bwdth,wght%5D.ttf",
    "NotoSerifTamil.ttf": "notoseriftamil/NotoSerifTamil%5Bwdth,wght%5D.ttf",
    "NotoSerifTelugu.ttf": "notoseriftelugu/NotoSerifTelugu%5Bwght%5D.ttf",
    "NotoSerifGujarati.ttf": "notoserifgujarati/NotoSerifGujarati%5Bwght%5D.ttf",
    "NotoSerifGurmukhi.ttf": "notoserifgurmukhi/NotoSerifGurmukhi%5Bwght%5D.ttf",
    "NotoSerifKannada.ttf": "notoserifkannada/NotoSerifKannada%5Bwght%5D.ttf",
    "NotoSerifMalayalam.ttf": "notoserifmalayalam/NotoSerifMalayalam%5Bwght%5D.ttf",
}


def main() -> int:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, path in FONTS.items():
        target = FONT_DIR / name
        if target.exists():
            print(f"ok      {name}")
            continue
        try:
            with urllib.request.urlopen(BASE + path, timeout=60) as resp:
                target.write_bytes(resp.read())
            print(f"fetched {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAILED  {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
