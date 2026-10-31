"""Generate the live demo's photo cast with Gemini: a new bride and groom (same styling as the
current photos, different faces), father, mother, brother, sister and two kids, plus a family
group photo of all of them. Everyone is fictional (AI-generated), so no one's consent is needed.

Needs GEMINI_API_KEY in .env. Writes to app/static/demo/ (used by every language demo):
    bride.jpg, groom.jpg, family.jpg   shown on the invitation (enhanced automatically)
    cast/<person>.jpg                  individual portraits of every family member
The previous photos are moved to app/static/demo/previous/.

    python scripts/make_demo_cast_ai.py            # generate everything (~9 images, ≈ ₹3.5 each)
    python scripts/make_demo_cast_ai.py --dry-run  # show the prompts only
Restart the server afterwards to update the demos.
"""
import io
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "demo"
STYLE = ("Photorealistic professional Indian wedding photography, royal Rajasthani palace backdrop with carved arches and "
         "marigold decor, warm golden-hour light, vibrant rich colours, sharp focus, natural skin texture. "
         "No text, no watermark, no logo.")

# person: (aspect, prompt, reference photo used for styling)
CAST = {
    "bride": ("3:4", "Portrait of a beautiful young Indian bride, waist-up, smiling. Same styling as the reference photo "
              "(red velvet bridal lehenga with gold zardozi, dupatta over the head, maang tikka, nath, layered kundan "
              "necklaces, red bangles, mehndi) but a DIFFERENT woman's face.", "bride.jpg"),
    "groom": ("3:4", "Portrait of a handsome young Indian groom, waist-up, confident smile. Same styling as the reference "
              "photo (ivory sherwani with gold embroidery, ivory safa with brooch, stole) but a DIFFERENT man's face.", "groom.jpg"),
    "father": ("3:4", "Portrait of the bride's father, Indian man in his late fifties with greying hair and moustache, "
               "warm proud smile, maroon bandhgala sherwani with gold buttons and a saffron safa.", None),
    "mother": ("3:4", "Portrait of the bride's mother, Indian woman in her early fifties, graceful smile, emerald silk "
               "Banarasi saree with gold border, gold necklace and earrings, bindi, hair in a bun with gajra.", None),
    "brother": ("3:4", "Portrait of the bride's younger brother, Indian man in his mid twenties, cheerful, navy blue "
                "embroidered kurta with Nehru jacket.", None),
    "sister": ("3:4", "Portrait of the bride's younger sister, Indian woman in her early twenties, joyful, pastel pink "
               "lehenga with mirror work, light jewellery.", None),
    "kids": ("4:3", "Two cute Indian children about 6 and 8 years old, a boy in a mustard kurta-pajama and a girl in a "
             "magenta lehenga, laughing together, wedding celebration.", None),
}
FAMILY_PROMPT = (
    "Group wedding family portrait, 4:3 landscape, of exactly the people in the reference photos, keeping each face, "
    "outfit and jewellery exactly as in their reference: the bride and groom in the centre, the mother and father on "
    "either side of them, the brother and sister standing just behind, and the two children in front. Everyone smiling "
    "and looking at the camera, natural poses, full group visible."
)


def generate(client, prompt: str, refs: list[Image.Image], aspect: str) -> Image.Image:
    from google.genai import types

    resp = client.models.generate_content(
        model=settings.gemini_image_model,
        contents=[f"{prompt} {STYLE}", *refs],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=aspect)),
    )
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            if part.inline_data and part.inline_data.data:
                return Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
    raise RuntimeError("Gemini returned no image")


def make_cast(client, demo_dir: Path = DEMO_DIR) -> dict[str, Path]:
    cast_dir = demo_dir / "cast"
    cast_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, Image.Image] = {}
    for person, (aspect, prompt, ref_name) in CAST.items():
        refs = [Image.open(demo_dir / ref_name)] if ref_name and (demo_dir / ref_name).exists() else []
        made[person] = generate(client, prompt, refs, aspect)
        made[person].save(cast_dir / f"{person}.jpg", quality=95)
        print(f"  ✓ {person}")
    family = generate(client, FAMILY_PROMPT, list(made.values()), "4:3")
    print("  ✓ family group photo")

    previous = demo_dir / "previous"
    previous.mkdir(exist_ok=True)
    for name in ("bride.jpg", "groom.jpg", "family.jpg", "family.ready.jpg"):
        if (demo_dir / name).exists():
            shutil.move(str(demo_dir / name), str(previous / name))
    made["bride"].save(demo_dir / "bride.jpg", quality=95)
    made["groom"].save(demo_dir / "groom.jpg", quality=95)
    family.save(demo_dir / "family.jpg", quality=95)
    return {name: demo_dir / f"{name}.jpg" for name in ("bride", "groom", "family")}


def main(args: list[str]) -> int:
    if "--dry-run" in args:
        for person, (aspect, prompt, ref) in CAST.items():
            print(f"[{person}, {aspect}{', ref ' + ref if ref else ''}] {prompt}\n")
        print(f"[family, 4:3, refs: all of the above] {FAMILY_PROMPT}")
        return 0
    if not settings.gemini_enabled:
        print("Set GEMINI_API_KEY in .env first (https://aistudio.google.com → Get API key).")
        return 1
    from google import genai

    print(f"Generating the demo cast with {settings.gemini_image_model} …")
    make_cast(genai.Client(api_key=settings.gemini_api_key))
    print(f"Done. Approx. cost ₹{settings.image_cost_inr * (len(CAST) + 1):.0f}. Restart the server to update every demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
