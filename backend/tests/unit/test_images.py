"""U10: image frames, multi-page TIFF and unreadable images (SPEC §6.4)."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.errors import CORRUPTED_FILE, ProcessingError
from app.pipeline import images

EVAL = Path(__file__).resolve().parents[3] / "datasets" / "eval"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_u10_multipage_tiff_has_two_ocr_pages(manifest):
    row = manifest["syn-scan_02"]
    path = EVAL / row["path"]

    pages = list(images.iter_image_pages(path))

    assert images.frame_count(path) == row["pages"] == 2
    assert [p.page_no for p in pages] == [1, 2]
    assert all(p.method == "ocr" and p.ocr_confidence is not None for p in pages)
    assert row["invoices"][0]["invoice_number"] in pages[0].text


def test_u10_truncated_png_is_corrupted(manifest, tmp_path):
    data = (EVAL / manifest["syn-clean_00"]["path"]).read_bytes()
    truncated = tmp_path / "truncated.png"
    truncated.write_bytes(data[: len(data) // 2])

    with pytest.raises(ProcessingError) as err:
        list(images.iter_image_pages(truncated))

    assert err.value.code == CORRUPTED_FILE


def test_unidentified_image_is_corrupted(tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(PNG_MAGIC + b"not really an image")

    with pytest.raises(ProcessingError) as err:
        images.frame_count(junk)

    assert err.value.code == CORRUPTED_FILE


def test_transparent_background_becomes_white(tmp_path):
    path = tmp_path / "alpha.png"
    Image.new("RGBA", (40, 20), (0, 0, 0, 0)).save(path)

    frames = list(images.iter_frames(path))

    assert len(frames) == 1
    assert frames[0].dtype == np.uint8 and frames[0].shape == (20, 40)
    assert int(frames[0].min()) == 255


def test_exif_orientation_is_applied(tmp_path):
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise when displayed
    Image.new("L", (60, 30), 255).save(path, exif=exif)

    assert next(images.iter_frames(path)).shape == (60, 30)


def test_render_frame_png_returns_the_requested_frame(manifest):
    path = EVAL / manifest["syn-scan_02"]["path"]

    assert images.render_frame_png(path, 2, 60).startswith(PNG_MAGIC)
    with pytest.raises(IndexError):
        images.render_frame_png(path, 3, 60)
