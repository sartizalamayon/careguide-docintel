"""U7-U9: Tesseract OCR with the preprocessing fallback (SPEC §6.4)."""

from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.pipeline import ocr
from app.pipeline.normalize import amount_variants

EVAL = Path(__file__).resolve().parents[3] / "datasets" / "eval"


def gray(row: dict) -> np.ndarray:
    with Image.open(EVAL / row["path"]) as img:
        return np.asarray(img.convert("L"))


def test_u7_clean_image_has_high_confidence_and_the_total(manifest):
    row = manifest["syn-clean_00"]

    result = ocr.ocr_page(gray(row))

    assert result.mean_conf > 80
    assert not result.used_preprocessing
    total = Decimal(row["invoices"][0]["total"])
    assert any(v in result.text for v in amount_variants(total))


def test_u8_phone_photo_uses_the_preprocessed_pass(manifest):
    row = manifest["syn-photo_03"]

    result = ocr.ocr_page(gray(row))

    assert result.used_preprocessing
    assert result.mean_conf > 70
    assert result.word_count >= 20


def test_u9_blank_page_has_no_text(manifest):
    row = manifest["syn-blank_page"]

    result = ocr.ocr_page(gray(row))

    assert result.word_count < 3
    assert result.text == ""


def test_narrow_images_are_upscaled_to_2480_px():
    img = np.full((700, 500), 255, dtype=np.uint8)

    assert ocr.upscale(img).shape == (3472, 2480)
    assert ocr.upscale(np.full((10, 2000), 255, dtype=np.uint8)).shape == (10, 2000)


def _rotate(img: np.ndarray, degrees: float) -> np.ndarray:
    height, width = img.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    return cv2.warpAffine(img, matrix, (width, height), borderValue=255)


def test_deskew_straightens_small_angles_only(manifest):
    page = gray(manifest["syn-clean_00"])

    assert abs(ocr.skew_angle(ocr.deskew(_rotate(page, 3)))) < 0.3
    tilted = _rotate(page, 20)
    assert ocr.deskew(tilted) is tilted
