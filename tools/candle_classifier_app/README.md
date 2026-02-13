# Candle Classifier App

Standalone utility for calibrating HSV thresholds/ROI and classifying chart PNG files by red/yellow/none candle state.

## Features

- **Calibration mode (Streamlit UI)**
  - Upload/select sample charts.
  - Tune ROI (`x,y,width,height`) with live preview box.
  - Tune HSV ranges for red + yellow masks.
  - Preview overlay and live red/yellow pixel counts.
  - Save settings to `classifier_config.json`.

- **Batch mode**
  - Process all `*.png` files in an input folder.
  - Emit CSV report with: `filename,label,red_pixels,yellow_pixels`.
  - Optional upload of each image + classification to `/api/uploads/charts`.

## Requirements

Standalone app dependencies:

```bash
pip install streamlit opencv-python numpy requests
```

> `flask` is **not** required to run the standalone Streamlit app.

If you also want to run the backend API locally, install backend deps separately:

```bash
pip install -r ../../backend/requirements.txt
```

## Files

- `streamlit_app.py` - UI app with Calibration + Batch tabs.
- `batch_classify.py` - CLI fallback for batch processing.
- `classifier.py` - shared classifier logic.
- `classifier_config.json` - saved/default config.

## 1) Calibration mode (UI)

Run:

```bash
cd tools/candle_classifier_app
streamlit run streamlit_app.py
```

Expected output (terminal):

```text
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

Workflow:

1. In **Mode**, keep `Calibration` selected.
2. Upload a sample `.png` chart.
3. Adjust ROI sliders and HSV ranges.
4. Check mask overlay + `Red pixels` / `Yellow pixels` metrics.
5. Click **Save classifier_config.json**.

Expected output (UI): success message similar to:

```text
Saved config to /.../tools/candle_classifier_app/classifier_config.json
```

## 2) Batch mode (UI)

Run the same app:

```bash
cd tools/candle_classifier_app
streamlit run streamlit_app.py
```

Workflow:

1. Switch to **Batch** mode.
2. Set input folder containing `.png` files (or click **Browse folder (Windows Explorer)**).
3. Set output CSV path (or click **Browse output CSV**).
4. Optional: enable upload and keep endpoint as `/api/uploads/charts` compatible URL
   (example: `http://localhost:8000/api/uploads/charts`).
5. Run classification.

Expected output (UI):

```text
Processed N image(s). CSV saved to /.../classification_report.csv
```

> Note: Browse buttons use a native dialog (Windows Explorer on Windows) via `tkinter`.
> On headless/Linux environments where GUI dialogs are unavailable, enter paths manually.

## 3) Batch mode (CLI fallback)

Run:

```bash
cd tools/candle_classifier_app
python batch_classify.py \
  --input-folder ./sample_charts \
  --config ./classifier_config.json \
  --output-csv ./classification_report.csv
```

Expected output:

```text
Processed N images. Report: classification_report.csv
```

### Optional upload in CLI

```bash
python batch_classify.py \
  --input-folder ./sample_charts \
  --config ./classifier_config.json \
  --output-csv ./classification_report.csv \
  --upload-endpoint http://localhost:8000/api/uploads/charts
```

If upload fails for a file, the classifier continues and logs warning lines such as:

```text
WARN upload failed for chart_001.png: ...
```

## CSV format

Generated CSV (`classification_report.csv`):

```csv
filename,label,red_pixels,yellow_pixels
chart_001.png,red,1243,932
chart_002.png,yellow,421,1102
```
