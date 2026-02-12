# Charts Library

A React + Flask application for saving and browsing PNG trading charts by ticker and date.

## Architecture

- **Frontend:** React (Vite) app in `frontend/`.
  - UI entry point: `frontend/src/App.jsx`
  - Shared chart helpers: `frontend/src/lib/chartHelpers.js`
- **Backend:** Flask API in `backend/`.
  - Runtime entry point: `backend/app.py`
  - App factory and route wiring: `backend/charts_api/app_factory.py` and `backend/charts_api/routes.py`
  - Storage services:
    - local filesystem: `backend/charts_api/local_storage.py`
    - Cloudinary external mode: `backend/charts_api/cloudinary_storage.py`

The frontend always calls the Flask API (`/api/*`).
Storage is selected by backend `STORAGE_MODE`:
- `local`: files on disk (`LOCAL_STORAGE_DIR`)
- `external`: Cloudinary (free tier supported)

## Quick start

### Docker (recommended)

```bash
docker compose up --build --watch
```

- Frontend (Vite dev server with hot reload): http://localhost:8080
- Backend (Flask debug server with auto-reload): http://localhost:5000

### Backend (local)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Frontend (local)

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` to the backend via `VITE_API_PROXY_TARGET` (defaults to `http://localhost:5000` locally).

For Docker development (`docker compose up --build --watch`), the frontend service sets `VITE_API_BASE_URL=http://localhost:5000` so the browser calls Flask directly and does not depend on Vite proxy DNS inside the container network.

## Testing

### Backend tests

```bash
pytest backend/tests -q
```

### Frontend tests

```bash
npm --prefix frontend run test
```

## Storage modes

### 1) Local storage mode

Use backend environment variables:

- `STORAGE_MODE=local`
- `LOCAL_STORAGE_DIR=/path/to/storage` (optional; defaults to `backend/storage`)

The Flask API reads/writes chart PNG files and notes on disk.

### 2) External storage mode (Cloudinary)

Use backend environment variables:

- `STORAGE_MODE=external`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- Optional: `CLOUDINARY_FOLDER=charts-library`

In this mode, the same Flask API endpoints use Cloudinary for upload/list/delete/file access.

## API upload endpoints

The backend now provides two multipart upload endpoints with the same validation rules for `ticker`, `date`, `notes`, checklist fields, and PNG file type checks:

- `POST /api/charts` for the website upload flow (expects file field `chart`)
- `POST /api/uploads/charts` for external/future processing apps (accepts file field `image` and also `chart` for compatibility)

Example using the processing-app endpoint:

```bash
curl -X POST http://localhost:5000/api/uploads/charts \
  -F ticker=AAPL \
  -F date=2026-02-12 \
  -F notes='Uploaded by processor' \
  -F image=@./chart.png
```

## Deploying frontend on Netlify + backend on Render

This is the recommended hosted setup.

### 1) Deploy backend to Render

Use these settings in Render (Web Service):

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`
- Health check path: `/api/health`

Choose one backend storage mode:

- **Local mode on Render**
  - `STORAGE_MODE=local`
  - `LOCAL_STORAGE_DIR=/opt/render/project/src/backend/storage`
  - Add a persistent disk mounted at `/opt/render/project/src/backend/storage`
- **Cloudinary mode on Render**
  - `STORAGE_MODE=external`
  - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
  - Optional `CLOUDINARY_FOLDER`

### 2) Deploy frontend to Netlify

Use these settings in Netlify:

- Base directory: repo root
- Build command: `npm --prefix frontend ci && npm --prefix frontend run build`
- Publish directory: `frontend/dist`

Set this Netlify environment variable so the browser calls Flask on Render:

- `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`

### 3) Verify

After deploy:

- Open Netlify site
- Confirm ticker list loads
- Upload a PNG
- Confirm preview image loads
- Confirm delete works

## Netlify config

`netlify.toml` is configured for static SPA hosting (frontend only). API requests are expected to go to Flask backend via `VITE_API_BASE_URL`.

## TradingView batch image export script (local automation)

A helper script is included at `scripts/tradingview_export.py` for local, user-driven TradingView automation.

### What it does

- reads tickers from a text file (`tickers.txt`, one symbol per line)
- opens TradingView chart page in a persistent Chromium profile
- lets you do a one-time manual login + indicator/layout setup
- loops each ticker, opens TradingView **Symbol Search** (top-left), and saves via the camera menu (top-right)

### Setup

```bash
pip install playwright
playwright install chromium
```

### Usage

```bash
python scripts/tradingview_export.py --tickers tickers.txt --out tv_exports --profile tv_profile
```

Options:

- `--delay 0.0` delay between symbols (max speed)
- `--symbol-wait-ms 900` post-symbol settle wait (default tuned for reliability)
- `--headless` run without UI (not recommended for TradingView)
- `--dry-run` only validate and print tickers

Note: the script intentionally closes the `Search tool or function` dialog if it appears, re-clicks the top-left symbol entry point, and verifies `Symbol Search` stays open before typing.
