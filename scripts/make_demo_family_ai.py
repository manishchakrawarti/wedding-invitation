"""Generate a photorealistic family portrait for a demo, with the bride and groom plus both sets of parents.

Uses Gemini image generation, so GEMINI_API_KEY must be set in .env. The bride's and groom's photos
from app/static/demo/<lang>/ are sent as references and kept recognisable. The result is saved as
family.jpg (the demo loader enhances it), replacing the couple frame (family.ready.jpg).

    python scripts/make_demo_family_ai.py en hi
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "demo"
PROMPT = (
    "Create one photorealistic Indian wedding family portrait, 4:3 landscape. In the centre stand the bride and the "
    "groom from the two reference photos: keep their faces, expressions, outfits and jewellery exactly as in the "
    "references. Around them stand their four parents: the bride's mother and father on her side and the groom's "
    "mother and father on his side, all in their fifties, smiling warmly, in elegant traditional wedding attire "
    "(silk sarees with gold borders and jewellery for the mothers; sherwani or kurta with safa for the fathers). "
    "Royal palace courtyard with marigold garlands, warm golden-hour light, vibrant rich colours, sharp focus, "
    "professional wedding photography. No text, no watermark."
)


def main(langs: list[str]) -> int:
    if not settings.gemini_enabled:
        print("Set GEMINI_API_KEY in .env first.")
        return 1
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    for lang in langs:
        folder = DEMO_DIR / lang
        bride, groom = folder / "bride.jpg", folder / "groom.jpg"
        if not (bride.exists() and groom.exists()):
            print(f"{lang}: needs bride.jpg and groom.jpg in {folder}")
            continue
        resp = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=[PROMPT, Image.open(bride), Image.open(groom)],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="4:3")),
        )
        data = next((p.inline_data.data for c in resp.candidates or [] for p in (c.content.parts or []) if p.inline_data), None)
        if not data:
            print(f"{lang}: Gemini returned no image")
            continue
        Image.open(io.BytesIO(data)).convert("RGB").save(folder / "family.jpg", quality=95)
        (folder / "family.ready.jpg").unlink(missing_ok=True)
        print(f"{lang}: saved {folder / 'family.jpg'}; restart the server to update the demo (cost ≈ ₹{settings.image_cost_inr})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["en", "hi"]))
