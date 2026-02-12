from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from classifier import (
    ClassifierConfig,
    HSVRange,
    ROI,
    build_overlay,
    classify_image,
    list_png_images,
    load_config,
    save_config,
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "classifier_config.json"


st.set_page_config(page_title="Candle Classifier", layout="wide")
st.title("Candle Color Classifier")

mode = st.sidebar.radio("Mode", ["Calibration", "Batch"])
config_path = Path(st.sidebar.text_input("Config file", str(DEFAULT_CONFIG_PATH))).expanduser()
config = load_config(config_path)


def _image_with_roi_box(image_bgr: np.ndarray, roi: ROI) -> np.ndarray:
    preview = image_bgr.copy()
    x1, y1 = roi.x, roi.y
    x2, y2 = roi.x + roi.width, roi.y + roi.height
    cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
    return preview


if mode == "Calibration":
    st.header("Calibration mode")
    upload = st.file_uploader("Upload sample chart PNG", type=["png"])

    if upload is not None:
        file_bytes = np.asarray(bytearray(upload.read()), dtype=np.uint8)
        image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if image_bgr is None:
            st.error("Could not decode image")
            st.stop()

        h, w = image_bgr.shape[:2]

        st.subheader("ROI")
        col1, col2 = st.columns(2)
        with col1:
            roi_x = st.slider("ROI x", 0, max(0, w - 1), min(config.roi.x, max(0, w - 1)))
            roi_y = st.slider("ROI y", 0, max(0, h - 1), min(config.roi.y, max(0, h - 1)))
        with col2:
            roi_w = st.slider("ROI width", 1, max(1, w - roi_x), min(config.roi.width, max(1, w - roi_x)))
            roi_h = st.slider("ROI height", 1, max(1, h - roi_y), min(config.roi.height, max(1, h - roi_y)))

        st.subheader("HSV thresholds")

        def hsv_range_editor(prefix: str, hsv_range: HSVRange) -> HSVRange:
            c1, c2 = st.columns(2)
            with c1:
                lower_h = st.slider(f"{prefix} lower H", 0, 180, int(hsv_range.lower[0]))
                lower_s = st.slider(f"{prefix} lower S", 0, 255, int(hsv_range.lower[1]))
                lower_v = st.slider(f"{prefix} lower V", 0, 255, int(hsv_range.lower[2]))
            with c2:
                upper_h = st.slider(f"{prefix} upper H", 0, 180, int(hsv_range.upper[0]))
                upper_s = st.slider(f"{prefix} upper S", 0, 255, int(hsv_range.upper[1]))
                upper_v = st.slider(f"{prefix} upper V", 0, 255, int(hsv_range.upper[2]))
            return HSVRange((lower_h, lower_s, lower_v), (upper_h, upper_s, upper_v))

        red1 = hsv_range_editor("Red #1", config.red_range_1)
        red2 = hsv_range_editor("Red #2", config.red_range_2)
        yellow = hsv_range_editor("Yellow", config.yellow_range)
        threshold = st.number_input("Red-vs-yellow label threshold", value=int(config.label_threshold), step=1)

        live_config = ClassifierConfig(red_range_1=red1, red_range_2=red2, yellow_range=yellow, roi=ROI(roi_x, roi_y, roi_w, roi_h), label_threshold=int(threshold))
        result = classify_image(image_bgr, live_config)
        overlay = build_overlay(result["roi_image"], result["red_mask"], result["yellow_mask"])

        st.subheader("Preview")
        p1, p2 = st.columns(2)
        with p1:
            st.image(cv2.cvtColor(_image_with_roi_box(image_bgr, live_config.roi), cv2.COLOR_BGR2RGB), caption="ROI preview", use_container_width=True)
        with p2:
            st.image(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB), caption="HSV mask overlay (red/yellow)", use_container_width=True)

        st.metric("Red pixels", result["red_pixels"])
        st.metric("Yellow pixels", result["yellow_pixels"])
        st.metric("Predicted label", result["label"])

        if st.button("Save classifier_config.json"):
            save_config(live_config, config_path)
            st.success(f"Saved config to {config_path}")

    else:
        st.info("Upload a sample PNG to calibrate ROI and HSV ranges.")

if mode == "Batch":
    st.header("Batch mode")
    input_folder = Path(st.text_input("Input folder containing PNGs", str(BASE_DIR))).expanduser()
    upload_enabled = st.checkbox("POST each result to /api/uploads/charts")
    endpoint = st.text_input("Upload endpoint", "http://localhost:8000/api/uploads/charts")
    output_csv = Path(st.text_input("Output CSV path", str(BASE_DIR / "classification_report.csv"))).expanduser()

    if st.button("Run batch classification"):
        if not input_folder.exists():
            st.error(f"Input folder does not exist: {input_folder}")
            st.stop()

        rows = []
        images = list(list_png_images(input_folder))
        if not images:
            st.warning("No PNG files found in input folder")
            st.stop()

        from classifier import upload_classification  # local import to keep start-up cheap

        for path in images:
            img = cv2.imread(str(path))
            if img is None:
                rows.append((path.name, "decode_error", 0, 0))
                continue

            result = classify_image(img, config)
            rows.append((path.name, result["label"], result["red_pixels"], result["yellow_pixels"]))

            if upload_enabled:
                try:
                    response = upload_classification(endpoint, path, result)
                    if response.status_code >= 300:
                        st.warning(f"Upload failed for {path.name}: {response.status_code} {response.text}")
                except Exception as exc:
                    st.warning(f"Upload failed for {path.name}: {exc}")

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        output_csv.write_text("filename,label,red_pixels,yellow_pixels\n" + "\n".join(
            f"{filename},{label},{red_pixels},{yellow_pixels}" for filename, label, red_pixels, yellow_pixels in rows
        ))

        st.success(f"Processed {len(rows)} image(s). CSV saved to {output_csv}")
        st.dataframe(rows, use_container_width=True)
