from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

from classifier import classify_image, list_png_images, load_config, upload_classification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch classify chart PNG files by red/yellow candle dominance")
    parser.add_argument("--input-folder", required=True, type=Path, help="Folder containing .png chart files")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("classifier_config.json"), help="Path to classifier_config.json")
    parser.add_argument("--output-csv", type=Path, default=Path(__file__).with_name("classification_report.csv"), help="CSV output path")
    parser.add_argument("--upload-endpoint", type=str, default=None, help="Optional endpoint, e.g. http://localhost:8000/api/uploads/charts")
    parser.add_argument("--timeout", type=int, default=20, help="Upload timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.input_folder.exists():
        raise SystemExit(f"Input folder does not exist: {args.input_folder}")

    config = load_config(args.config)
    images = list(list_png_images(args.input_folder))
    if not images:
        raise SystemExit(f"No PNG images found in {args.input_folder}")

    rows = []
    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            rows.append((image_path.name, "decode_error", 0, 0))
            continue

        result = classify_image(image, config)
        rows.append((image_path.name, result["label"], result["red_pixels"], result["yellow_pixels"]))

        if args.upload_endpoint:
            try:
                response = upload_classification(args.upload_endpoint, image_path, result, timeout=args.timeout)
                response.raise_for_status()
            except Exception as exc:
                print(f"WARN upload failed for {image_path.name}: {exc}")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["filename", "label", "red_pixels", "yellow_pixels"])
        writer.writerows(rows)

    print(f"Processed {len(rows)} images. Report: {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
