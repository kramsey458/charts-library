from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import requests

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from charts_api.candle_classifier import (  # noqa: E402
    CandleClassifierConfig,
    HSVRange,
    ROI,
    classify_candle,
    load_classifier_config,
)


ClassifierConfig = CandleClassifierConfig


def load_config(path: Path) -> ClassifierConfig:
    return load_classifier_config(path)


def save_config(config: ClassifierConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2))


def crop_to_roi(image_bgr: np.ndarray, roi: ROI) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    x = min(max(0, roi.x), max(0, w - 1))
    y = min(max(0, roi.y), max(0, h - 1))
    width = max(1, min(roi.width, w - x))
    height = max(1, min(roi.height, h - y))
    return image_bgr[y : y + height, x : x + width]


def _range_mask(hsv_img: np.ndarray, hsv_range: HSVRange) -> np.ndarray:
    lower = np.array(hsv_range.lower, dtype=np.uint8)
    upper = np.array(hsv_range.upper, dtype=np.uint8)
    return cv2.inRange(hsv_img, lower, upper)


def classify_image(image_bgr: np.ndarray, config: ClassifierConfig) -> dict:
    result = classify_candle(image_bgr, config=config)
    roi_img = crop_to_roi(image_bgr, config.roi)
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)

    red_mask_1 = _range_mask(hsv, config.red_range_1)
    red_mask_2 = _range_mask(hsv, config.red_range_2)
    red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)
    yellow_mask = _range_mask(hsv, config.yellow_range)

    return {
        "label": result["label"],
        "red_pixels": result["scores"]["red_pixels"],
        "yellow_pixels": result["scores"]["yellow_pixels"],
        "red_mask": red_mask,
        "yellow_mask": yellow_mask,
        "roi_image": roi_img,
    }


def build_overlay(roi_image: np.ndarray, red_mask: np.ndarray, yellow_mask: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    overlay = roi_image.copy()
    overlay[red_mask > 0] = (0, 0, 255)
    overlay[yellow_mask > 0] = (0, 255, 255)
    blended = cv2.addWeighted(overlay, alpha, roi_image, 1 - alpha, 0)
    return blended


def list_png_images(folder: Path) -> Iterable[Path]:
    for path in sorted(folder.glob("*.png")):
        if path.is_file():
            yield path


def upload_classification(
    endpoint: str,
    image_path: Path,
    result: dict,
    timeout: int = 20,
) -> requests.Response:
    with image_path.open("rb") as fp:
        files = {"chart": (image_path.name, fp, "image/png")}
        data = {
            "label": result["label"],
            "red_pixels": str(result["red_pixels"]),
            "yellow_pixels": str(result["yellow_pixels"]),
        }
        return requests.post(endpoint, files=files, data=data, timeout=timeout)
