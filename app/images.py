"""Image intake: validate the upload and shrink it before sending to the vision model.

Downscaling is the single biggest latency lever: a 12 MP phone photo is mostly
wasted bytes for reading label text.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EDGE_PX = 1568  # largest edge the vision model uses without internal resizing


class ImageError(ValueError):
    """Raised with a message that is safe to show the user."""


def prepare_image(data: bytes) -> bytes:
    """Return a JPEG of the label, upright and resized. Raises ImageError for bad uploads."""
    if not data:
        raise ImageError("No picture was uploaded. Please choose a label image.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("That picture is too large (over 10 MB). Please use a smaller image.")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise ImageError("That file is not a picture we can open. Please upload a JPG or PNG.")

    image = ImageOps.exif_transpose(image)  # phone photos are often stored sideways
    image = image.convert("RGB")
    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()
