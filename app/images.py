"""Image intake: validate the upload and shrink it before sending to the vision model.

Downscaling is the single biggest latency lever: a 12 MP phone photo is mostly
wasted bytes for reading label text.
"""

import io

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EDGE_PX = 1568  # largest edge the vision model uses without internal resizing
# Covers 48 MP phone cameras. A small file that claims more pixels than this is a
# "decompression bomb" that would exhaust memory when decoded, so it is refused unopened.
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(ValueError):
    """Raised with a message that is safe to show the user."""


async def read_upload(upload: UploadFile) -> bytes:
    """Read at most one byte past the limit, so an enormous upload never lands in memory whole."""
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("That picture is too large (over 10 MB). Please use a smaller image.")
    return data


def prepare_image(data: bytes) -> bytes:
    """Return a JPEG of the label, upright and resized. Raises ImageError for bad uploads."""
    if not data:
        raise ImageError("No picture was uploaded. Please choose a label image.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("That picture is too large (over 10 MB). Please use a smaller image.")

    try:
        image = Image.open(io.BytesIO(data))  # reads the header only; pixels are not decoded yet
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise ImageError("That picture has too many pixels to process. Please use a smaller image.")
        image.draft("RGB", (MAX_EDGE_PX, MAX_EDGE_PX))  # JPEGs decode straight at reduced size: much faster
        image.load()
    except ImageError:
        raise
    except Image.DecompressionBombError:  # Pillow's own guard, for files far over the limit
        raise ImageError("That picture has too many pixels to process. Please use a smaller image.")
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageError("That file is not a picture we can open. Please upload a JPG or PNG.")

    image = ImageOps.exif_transpose(image)  # phone photos are often stored sideways
    image = image.convert("RGB")
    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()
