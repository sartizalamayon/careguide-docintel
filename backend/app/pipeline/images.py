"""PNG / JPG / TIFF frames to OCR text (SPEC §6.4)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.errors import CORRUPTED_FILE, ProcessingError
from app.log import log
from app.pipeline.ocr import ocr_page
from app.pipeline.types import PageText

Image.MAX_IMAGE_PIXELS = 120_000_000

_IMAGE_ERRORS = (UnidentifiedImageError, OSError, Image.DecompressionBombError)


@contextmanager
def _guarded() -> Iterator[None]:
    """Map PIL open/decode failures to CORRUPTED_FILE."""
    try:
        yield
    except _IMAGE_ERRORS as exc:
        log.warning("image_read_failed", error=type(exc).__name__)
        raise ProcessingError(CORRUPTED_FILE, "The image cannot be read.") from exc


def _frames(img: Image.Image) -> Iterator[Image.Image]:
    """Seek through every frame like ImageSequence, but skip directories without image dimensions.

    Such directories carry only metadata (e.g. a C2PA manifest IFD in a TIFF); PIL raises TypeError on them.
    """
    index = 0
    while True:
        try:
            img.seek(index)
        except EOFError:
            return
        except TypeError:
            log.warning("image_frame_skipped", frame=index + 1)
        else:
            yield img
        index += 1


def frame_count(path: Path) -> int:
    with _guarded(), Image.open(path) as img:
        return sum(1 for _ in _frames(img))


def iter_frames(path: Path) -> Iterator[np.ndarray]:
    """Yield every frame as an upright grayscale array."""
    with _guarded(), Image.open(path) as img:
        for frame in _frames(img):
            yield np.asarray(_to_gray(ImageOps.exif_transpose(frame)))


def iter_image_pages(path: Path) -> Iterator[PageText]:
    for index, gray in enumerate(iter_frames(path)):
        result = ocr_page(gray)
        yield PageText(
            page_no=index + 1,
            text=result.text,
            method="ocr",
            ocr_confidence=result.mean_conf,
            word_count=result.word_count,
        )


def render_frame_png(path: Path, frame_no: int, dpi: int) -> bytes:
    """PNG of one 1-based frame (image endpoint). `dpi` is ignored: images are returned at their own size.

    Raises IndexError for a frame that does not exist.
    """
    with _guarded(), Image.open(path) as img:
        for number, frame in enumerate(_frames(img), start=1):
            if number == frame_no:
                out = io.BytesIO()
                _to_gray(ImageOps.exif_transpose(frame)).save(out, format="PNG")
                return out.getvalue()
    raise IndexError(f"frame {frame_no} out of range")


def _to_gray(img: Image.Image) -> Image.Image:
    """Grayscale, with transparent areas shown as white paper rather than black."""
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, rgba)
    return img.convert("L")
