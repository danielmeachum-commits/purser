"""Inky Impression 7.3" 7-color palette + quantization helpers.

The Pimoroni `inky` library accepts any PIL image and quantizes internally,
but doing the quantization here means the API returns bytes the Pi can blit
straight to the panel — no Pi-side color work, just `inky.set_image(img)`.
"""

from __future__ import annotations

from PIL import Image

# Palette indices match the inky library's saturated-color constants.
# Saturated values are what `inky` uses to build its own palette image, so
# quantizing against them lines up with the panel's actual dye colors.
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 140, 0)

INKY_7COLOR: tuple[tuple[int, int, int], ...] = (
    BLACK,
    WHITE,
    GREEN,
    BLUE,
    RED,
    YELLOW,
    ORANGE,
)


def _palette_image() -> Image.Image:
    """Build a PIL palette image PIL can quantize against."""
    flat: list[int] = []
    for r, g, b in INKY_7COLOR:
        flat.extend((r, g, b))
    # PIL requires 256 RGB triples; pad with black.
    flat.extend([0] * (768 - len(flat)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


_PALETTE = _palette_image()


def quantize_to_inky(img: Image.Image, *, dither: bool = False) -> Image.Image:
    """Quantize `img` (RGB) to the Inky palette.

    `dither=False` (default) snaps each pixel to the nearest palette color.
    That keeps black text crisp at the cost of some banding in color regions
    — the right trade for a finance dashboard where the bars are already
    solid colors. Pass `dither=True` for photo-like content.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    return img.quantize(palette=_PALETTE, dither=mode)
