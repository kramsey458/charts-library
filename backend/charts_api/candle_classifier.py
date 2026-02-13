from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class HSVRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]


@dataclass(frozen=True)
class ROI:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class CandleClassifierConfig:
    red_range_1: HSVRange
    red_range_2: HSVRange
    yellow_range: HSVRange
    roi: ROI
    min_pixels: int = 100
    dominance_ratio: float = 1.25
    legacy_label_threshold: int = 0

    @classmethod
    def default(cls) -> "CandleClassifierConfig":
        # Top-panel ROI defaults for invariant chart layouts.
        return cls(
            red_range_1=HSVRange((0, 80, 80), (10, 255, 255)),
            red_range_2=HSVRange((170, 80, 80), (180, 255, 255)),
            yellow_range=HSVRange((18, 80, 80), (40, 255, 255)),
            roi=ROI(x=0, y=0, width=1200, height=300),
            min_pixels=100,
            dominance_ratio=1.25,
            legacy_label_threshold=0,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandleClassifierConfig":
        defaults = cls.default()
        has_new_thresholds = "min_pixels" in payload or "dominance_ratio" in payload
        legacy_label_threshold = int(payload.get("label_threshold", 0)) if not has_new_thresholds else 0
        min_pixels = int(payload.get("min_pixels", defaults.min_pixels if has_new_thresholds else 0))
        dominance_ratio = float(payload.get("dominance_ratio", defaults.dominance_ratio if has_new_thresholds else 1.0))

        return cls(
            red_range_1=HSVRange(
                tuple(payload.get("red_range_1", {}).get("lower", defaults.red_range_1.lower)),
                tuple(payload.get("red_range_1", {}).get("upper", defaults.red_range_1.upper)),
            ),
            red_range_2=HSVRange(
                tuple(payload.get("red_range_2", {}).get("lower", defaults.red_range_2.lower)),
                tuple(payload.get("red_range_2", {}).get("upper", defaults.red_range_2.upper)),
            ),
            yellow_range=HSVRange(
                tuple(payload.get("yellow_range", {}).get("lower", defaults.yellow_range.lower)),
                tuple(payload.get("yellow_range", {}).get("upper", defaults.yellow_range.upper)),
            ),
            roi=ROI(**payload.get("roi", asdict(defaults.roi))),
            min_pixels=min_pixels,
            dominance_ratio=dominance_ratio,
            legacy_label_threshold=legacy_label_threshold,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("legacy_label_threshold", None)
        return payload


def load_classifier_config(config_path: str | Path | None = None) -> CandleClassifierConfig:
    path = Path(config_path) if config_path else Path(__file__).with_name("classifier_config.json")
    if not path.exists():
        return CandleClassifierConfig.default()
    payload = json.loads(path.read_text())
    return CandleClassifierConfig.from_dict(payload)


def _decode_image(image_input: bytes | str | Path | np.ndarray) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        return image_input
    if isinstance(image_input, (str, Path)):
        image = cv2.imread(str(image_input), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unable to decode image from path: {image_input}")
        return image
    if isinstance(image_input, (bytes, bytearray)):
        arr = np.frombuffer(image_input, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image from bytes")
        return image
    raise TypeError("image_input must be bytes, path-like, or numpy.ndarray")


def _crop_to_roi(image_bgr: np.ndarray, roi: ROI) -> np.ndarray:
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


def classify_candle(
    image_input: bytes | str | Path | np.ndarray,
    config: CandleClassifierConfig | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = config or load_classifier_config(config_path)
    image = _decode_image(image_input)
    roi_image = _crop_to_roi(image, cfg.roi)

    hsv = cv2.cvtColor(roi_image, cv2.COLOR_BGR2HSV)
    red_mask = cv2.bitwise_or(_range_mask(hsv, cfg.red_range_1), _range_mask(hsv, cfg.red_range_2))
    yellow_mask = _range_mask(hsv, cfg.yellow_range)

    red_pixels = int(np.count_nonzero(red_mask))
    yellow_pixels = int(np.count_nonzero(yellow_mask))

    label = "none"
    if cfg.legacy_label_threshold > 0:
        score = red_pixels - yellow_pixels
        if score > cfg.legacy_label_threshold:
            label = "red"
        elif score < -cfg.legacy_label_threshold:
            label = "yellow"
    else:
        if red_pixels >= cfg.min_pixels and red_pixels > yellow_pixels * cfg.dominance_ratio:
            label = "red"
        elif yellow_pixels >= cfg.min_pixels and yellow_pixels > red_pixels * cfg.dominance_ratio:
            label = "yellow"

    return {
        "label": label,
        "scores": {
            "red_pixels": red_pixels,
            "yellow_pixels": yellow_pixels,
            "min_pixels": cfg.min_pixels,
            "dominance_ratio": cfg.dominance_ratio,
            "legacy_label_threshold": cfg.legacy_label_threshold,
            "roi_area": int(roi_image.shape[0] * roi_image.shape[1]),
        },
    }
