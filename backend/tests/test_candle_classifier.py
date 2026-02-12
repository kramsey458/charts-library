from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from charts_api.candle_classifier import classify_candle, load_classifier_config


def _encode_png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    return encoded.tobytes()


def test_classify_red_from_image_bytes() -> None:
    image = np.zeros((220, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (180, 140), (0, 0, 255), -1)

    result = classify_candle(_encode_png_bytes(image))

    assert result['label'] == 'red'
    assert result['scores']['red_pixels'] > result['scores']['yellow_pixels']


def test_classify_yellow_from_image_path(tmp_path: Path) -> None:
    image = np.zeros((220, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (30, 30), (210, 150), (0, 255, 255), -1)

    image_path = tmp_path / 'yellow.png'
    assert cv2.imwrite(str(image_path), image)

    result = classify_candle(image_path)

    assert result['label'] == 'yellow'
    assert result['scores']['yellow_pixels'] > result['scores']['red_pixels']


def test_classify_ignore_when_neither_color_meets_threshold() -> None:
    image = np.zeros((220, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (10, 10), (15, 15), (0, 0, 255), -1)
    cv2.rectangle(image, (30, 10), (35, 15), (0, 255, 255), -1)

    result = classify_candle(_encode_png_bytes(image))

    assert result['label'] == 'ignore'


def test_load_classifier_config_from_json(tmp_path: Path) -> None:
    config_path = tmp_path / 'classifier_config.json'
    config_path.write_text(
        json.dumps(
            {
                'red_range_1': {'lower': [0, 80, 80], 'upper': [10, 255, 255]},
                'red_range_2': {'lower': [170, 80, 80], 'upper': [180, 255, 255]},
                'yellow_range': {'lower': [18, 80, 80], 'upper': [40, 255, 255]},
                'roi': {'x': 0, 'y': 0, 'width': 320, 'height': 80},
                'min_pixels': 200,
                'dominance_ratio': 1.5,
            }
        )
    )

    config = load_classifier_config(config_path)

    assert config.roi.height == 80
    assert config.min_pixels == 200
    assert config.dominance_ratio == 1.5


def test_top_panel_roi_excludes_bottom_signal(tmp_path: Path) -> None:
    config_path = tmp_path / 'classifier_config.json'
    config_path.write_text(
        json.dumps(
            {
                'roi': {'x': 0, 'y': 0, 'width': 320, 'height': 100},
                'min_pixels': 50,
                'dominance_ratio': 1.2,
            }
        )
    )

    image = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (20, 160), (280, 230), (0, 0, 255), -1)

    result = classify_candle(_encode_png_bytes(image), config_path=config_path)

    assert result['label'] == 'ignore'
    assert result['scores']['red_pixels'] == 0
