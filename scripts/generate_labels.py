"""Generate synthetic test labels with a known answer key.

Each label is rendered from a spec, so we know exactly what text is printed on it.
Some labels carry deliberate compliance defects (wrong ABV, title-case warning, ...);
others carry photo defects (blur, glare, rotation, ...) to test how the reader copes.

Usage:  python scripts/generate_labels.py            # writes samples/labels/

The generated PNGs are committed, so this only needs re-running to change the set.
It uses macOS system fonts (Georgia, Arial); on other systems point FONT_DIR at
equivalent .ttf files.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "labels"
FONT_DIR = Path("/System/Library/Fonts/Supplemental")

STANDARD_WARNING_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic beverages during "
    "pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs "
    "your ability to drive a car or operate machinery, and may cause health problems."
)


@dataclass
class LabelSpec:
    name: str
    description: str
    brand_name: str = "OLD TOM DISTILLERY"
    class_type: str = "Kentucky Straight Bourbon Whiskey"
    alcohol_content: str | None = "45% Alc./Vol. (90 Proof)"
    net_contents: str | None = "750 mL"
    bottler_name_address: str | None = "Bottled by Old Tom Distillery, Bardstown, KY"
    country_of_origin: str | None = None
    warning_header: str = "GOVERNMENT WARNING:"
    warning_header_bold: bool = True
    warning_body: str = STANDARD_WARNING_BODY
    warning_font_size: int = 22
    background: str = "#f3ead7"
    # Photo defects applied after rendering.
    distortions: list[str] = field(default_factory=list)

    @property
    def government_warning_text(self) -> str:
        return f"{self.warning_header} {self.warning_body}"


SPECS = [
    LabelSpec("01_clean", "Clean label, everything correct."),
    LabelSpec("02_wrong_abv", "ABV on label differs from application.", alcohol_content="40% Alc./Vol. (80 Proof)"),
    LabelSpec("03_proof_mismatch", "Proof is not twice the ABV.", alcohol_content="45% Alc./Vol. (80 Proof)"),
    LabelSpec("04_title_case_warning", "Warning header in title case.", warning_header="Government Warning:"),
    LabelSpec("05_warning_not_bold", "Warning header not bold.", warning_header_bold=False),
    LabelSpec(
        "06_warning_reworded",
        "Warning body reworded.",
        warning_body=STANDARD_WARNING_BODY.replace("may cause health problems", "can cause health issues"),
    ),
    LabelSpec("07_missing_net_contents", "Net contents missing from label.", net_contents=None),
    LabelSpec(
        "08_stones_throw",
        "Different brand, mixed-case apostrophe brand name.",
        brand_name="STONE'S THROW",
        class_type="London Dry Gin",
        alcohol_content="47% Alc./Vol. (94 Proof)",
        bottler_name_address="Distilled and Bottled by Stone's Throw Spirits, Portland, OR",
    ),
    LabelSpec("09_fluid_ounces", "Net contents in US fluid ounces.", net_contents="25.4 FL. OZ."),
    LabelSpec("10_tiny_warning", "Warning printed in very small type.", warning_font_size=12),
    LabelSpec(
        "11_import_wine",
        "Imported wine with country of origin.",
        brand_name="Château Belle Rive",
        class_type="Bordeaux Red Wine",
        alcohol_content="13.5% Alc. by Vol.",
        bottler_name_address="Imported by Rive Imports LLC, New York, NY",
        country_of_origin="Product of France",
        background="#ecebe4",
    ),
    LabelSpec("12_blurred", "Out-of-focus photo.", distortions=["blur"]),
    LabelSpec("13_rotated", "Photo taken at an angle.", distortions=["rotate"]),
    LabelSpec("14_glare", "Bright glare across the label.", distortions=["glare"]),
    LabelSpec("15_low_resolution", "Very low resolution image.", distortions=["low_res"]),
    LabelSpec("16_dim_lighting", "Dark, low-contrast photo.", distortions=["dim"]),
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def render(spec: LabelSpec) -> Image.Image:
    width, height = 900, 1200
    img = Image.new("RGB", (width, height), spec.background)
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline="#5a3a1a", width=6)

    def centered(y: int, text: str, font: ImageFont.FreeTypeFont) -> None:
        # Shrink long lines so they always fit inside the border.
        while draw.textlength(text, font=font) > width - 120 and font.size > 14:
            font = font.font_variant(size=font.size - 2)
        x = (width - draw.textlength(text, font=font)) / 2
        draw.text((x, y), text, font=font, fill="#2b1a0b")

    centered(110, spec.brand_name, _font("Georgia Bold.ttf", 84))
    centered(330, spec.class_type, _font("Georgia Italic.ttf", 44))
    if spec.alcohol_content:
        centered(480, spec.alcohol_content, _font("Georgia.ttf", 40))
    if spec.net_contents:
        centered(550, spec.net_contents, _font("Georgia.ttf", 40))
    if spec.bottler_name_address:
        centered(650, spec.bottler_name_address, _font("Georgia.ttf", 26))
    if spec.country_of_origin:
        centered(700, spec.country_of_origin, _font("Georgia.ttf", 26))

    header_font = _font("Arial Bold.ttf" if spec.warning_header_bold else "Arial.ttf", spec.warning_font_size)
    body_font = _font("Arial.ttf", spec.warning_font_size)
    words = [(spec.warning_header, header_font)] + [(w, body_font) for w in spec.warning_body.split()]
    left, max_width, line_height = 70, width - 140, int(spec.warning_font_size * 1.45)
    x, y = left, 820
    for text, font in words:
        advance = draw.textlength(text + " ", font=font)
        if x + advance > left + max_width:
            x, y = left, y + line_height
        draw.text((x, y), text, font=font, fill="#111")
        x += advance
    return img


def distort(img: Image.Image, kind: str) -> Image.Image:
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(2.2))
    if kind == "rotate":
        return img.rotate(9, expand=True, fillcolor="#6b6b6b", resample=Image.BICUBIC)
    if kind == "glare":
        overlay = Image.new("L", img.size, 0)
        ImageDraw.Draw(overlay).ellipse([250, 300, 750, 700], fill=235)
        overlay = overlay.filter(ImageFilter.GaussianBlur(70))
        return Image.composite(Image.new("RGB", img.size, "white"), img, overlay)
    if kind == "low_res":
        small = img.resize((img.width // 3, img.height // 3), Image.BILINEAR)
        return small.resize(img.size, Image.NEAREST)
    if kind == "dim":
        img = ImageEnhance.Brightness(img).enhance(0.35)
        return ImageEnhance.Contrast(img).enhance(0.6)
    raise ValueError(f"unknown distortion {kind}")


def answer_key(spec: LabelSpec) -> dict:
    """The fields exactly as printed, matching ExtractedLabel's field names."""
    data = asdict(spec)
    return {
        "description": spec.description,
        "distortions": spec.distortions,
        "brand_name": spec.brand_name,
        "class_type": spec.class_type,
        "alcohol_content": spec.alcohol_content,
        "net_contents": spec.net_contents,
        "bottler_name_address": spec.bottler_name_address,
        "country_of_origin": spec.country_of_origin,
        "government_warning_text": spec.government_warning_text,
        "warning_header_appears_bold": data["warning_header_bold"],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    for spec in SPECS:
        img = render(spec)
        for kind in spec.distortions:
            img = distort(img, kind)
        img.save(OUT_DIR / f"{spec.name}.png")
        key[f"{spec.name}.png"] = answer_key(spec)
    (OUT_DIR / "answer_key.json").write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(SPECS)} labels and answer_key.json to {OUT_DIR}")


if __name__ == "__main__":
    main()
