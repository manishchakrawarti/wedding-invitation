"""Prompt templates (C4). One template per style lives in catalog.STYLES; this module
wraps it with the rules every invitation background must follow."""
from app.catalog import FUNCTIONS, STYLES

BASE_RULES = (
    "Portrait 4:5 format. Leave the central area (from about 18% to 68% of the height) calm and softly "
    "textured with no busy detail, because names and dates will be added there later. "
    "Absolutely no text, letters, numbers, calligraphy, logos or watermarks anywhere in the image. "
    "Print-quality, highly detailed, rich traditional Indian craftsmanship, balanced symmetrical composition."
)

COUPLE_RULES = (
    "Use the attached photo(s) of the couple: paint them as an elegant illustrated portrait in traditional "
    "wedding attire in the bottom third of the card, keeping their faces recognisable and true to the photo, "
    "natural skin tones, no distortion."
)


def build_prompt(style_key: str, card_key: str, with_photo: bool, revision_notes: str = "", occasion_name: str = "") -> str:
    style = STYLES[style_key]
    if occasion_name:
        occasion = f"{occasion_name} invitation"
    else:
        occasion = "wedding invitation" if card_key == "main" else f"{FUNCTIONS.get(card_key, card_key)} ceremony invitation"
    parts = [f"Create {style.prompt}. This is a {occasion} background.", BASE_RULES]
    if with_photo:
        parts.append(COUPLE_RULES)
    if revision_notes.strip():
        parts.append(f"Customer feedback to apply: {revision_notes.strip()}")
    return " ".join(parts)
