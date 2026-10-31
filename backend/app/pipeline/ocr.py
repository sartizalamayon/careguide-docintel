"""Tesseract OCR with an OpenCV preprocessing fallback pass (SPEC §6.4)."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

from app.pipeline.layout import Word, render

TESSERACT_CONFIG = "--oem 1 --psm 4"
MIN_WIDTH = 2000
TARGET_WIDTH = 2480
GOOD_CONF = 80.0
GOOD_WORDS = 20
MIN_TEXT_WORDS = 3
DESKEW_MIN_DEG = 0.3
DESKEW_MAX_DEG = 10.0


@dataclass
class OcrResult:
    text: str
    mean_conf: float
    word_count: int
    used_preprocessing: bool = False

    @property
    def score(self) -> float:
        return self.mean_conf * min(1.0, self.word_count / GOOD_WORDS)


def ocr_page(gray: np.ndarray) -> OcrResult:
    """OCR one grayscale page. Pass B (preprocessed) runs only when pass A looks weak; the better pass wins."""
    img = upscale(gray)
    result = run_tesseract(img)
    if result.mean_conf < GOOD_CONF or result.word_count < GOOD_WORDS:
        pass_b = run_tesseract(preprocess(img))
        pass_b.used_preprocessing = True
        both_empty = max(result.word_count, pass_b.word_count) < MIN_TEXT_WORDS
        result = pass_b if pass_b.score > result.score else result
    else:
        both_empty = result.word_count < MIN_TEXT_WORDS
    if both_empty:
        result.text = ""
    return result


def upscale(gray: np.ndarray) -> np.ndarray:
    height, width = gray.shape[:2]
    if width >= MIN_WIDTH:
        return gray
    new_height = round(height * TARGET_WIDTH / width)
    return cv2.resize(gray, (TARGET_WIDTH, new_height), interpolation=cv2.INTER_CUBIC)


def run_tesseract(img: np.ndarray) -> OcrResult:
    data = pytesseract.image_to_data(img, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT)
    words: list[Word] = []
    confs: list[float] = []
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        conf = float(data["conf"][i])
        if conf < 0 or not text:
            continue
        left, top = float(data["left"][i]), float(data["top"][i])
        words.append(Word(left, top, left + float(data["width"][i]), top + float(data["height"][i]), text))
        confs.append(conf)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return OcrResult(text=render(words), mean_conf=mean_conf, word_count=len(words))


def preprocess(gray: np.ndarray) -> np.ndarray:
    """Deskew, denoise and binarise (pass B)."""
    img = cv2.medianBlur(deskew(gray), 3)
    return cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def skew_angle(gray: np.ndarray) -> float:
    """Text skew in degrees from the minimum-area rectangle around the dark pixels."""
    _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    points = cv2.findNonZero(dark)
    if points is None:
        return 0.0
    angle = float(cv2.minAreaRect(points)[-1])
    return angle - 90.0 if angle > 45.0 else angle


def deskew(gray: np.ndarray) -> np.ndarray:
    angle = skew_angle(gray)
    if not DESKEW_MIN_DEG <= abs(angle) <= DESKEW_MAX_DEG:
        return gray
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
