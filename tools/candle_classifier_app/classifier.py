from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import requests


@dataclass
class HSVRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]


@dataclass
class ROI:
    x: int
    y: int
    width: int
    height: int


@dataclass
class ClassifierConfig:
    red_range_1: HSVRange
    red_range_2: HSVRange
    yellow_range: HSVRange
    roi: ROI
    label_threshold: int = 0

    @classmethod
    def default(cls, image_shape: tuple[int, int, int] | None = None) -> "ClassifierConfig":
        if image_shape:
            h, w = image_shape[:2]
            roi = ROI(0, 0, w, h)
        else:
            roi = ROI(0, 0, 1000, 1000)
        return cls(
            red_range_1=HSVRange((0, 80, 80), (10, 255, 255)),
            red_range_2=HSVRange((170, 80, 80), (180, 255, 255)),
            yellow_range=HSVRange((18, 80, 80), (40, 255, 255)),
            roi=roi,
            label_threshold=0,
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "ClassifierConfig":
        return cls(
            red_range_1=HSVRange(tuple(payload["red_range_1"]["lower"]), tuple(payload["red_range_1"]["upper"])),
            red_range_2=HSVRange(tuple(payload["red_range_2"]["lower"]), tuple(payload["red_range_2"]["upper"])),
            yellow_range=HSVRange(tuple(payload["yellow_range"]["lower"]), tuple(payload["yellow_range"]["upper"])),
            roi=ROI(**payload["roi"]),
            label_threshold=int(payload.get("label_threshold", 0)),
        )


def load_config(path: Path) -> ClassifierConfig:
    if not path.exists():
        return ClassifierConfig.default()
    payload = json.loads(path.read_text())
    return ClassifierConfig.from_dict(payload)


def save_config(config: ClassifierConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2))


def crop_to_roi(image_bgr: np.ndarray, roi: ROI) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    x = max(0, roi.x)
    y = max(0, roi.y)
    width = max(1, min(roi.width, w - x))
    height = max(1, min(roi.height, h - y))
    return image_bgr[y : y + height, x : x + width]


def _range_mask(hsv_img: np.ndarray, hsv_range: HSVRange) -> np.ndarray:
    lower = np.array(hsv_range.lower, dtype=np.uint8)
    upper = np.array(hsv_range.upper, dtype=np.uint8)
    return cv2.inRange(hsv_img, lower, upper)


def classify_image(image_bgr: np.ndarray, config: ClassifierConfig) -> dict:
    roi_img = crop_to_roi(image_bgr, config.roi)
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)

    red_mask_1 = _range_mask(hsv, config.red_range_1)
    red_mask_2 = _range_mask(hsv, config.red_range_2)
    red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)
    yellow_mask = _range_mask(hsv, config.yellow_range)

    red_pixels = int(np.count_nonzero(red_mask))
    yellow_pixels = int(np.count_nonzero(yellow_mask))
    score = red_pixels - yellow_pixels
    label = "red_dominant" if score > config.label_threshold else "yellow_dominant"

    return {
        "label": label,
        "red_pixels": red_pixels,
        "yellow_pixels": yellow_pixels,
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
