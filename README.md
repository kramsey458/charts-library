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


## AI chart analysis (synchronous v1)

Each chart now supports a persisted AI analysis object:

- `status`: `idle|running|completed|failed`
- `model`
- `prompt_version`
- `text`
- `error`
- `started_at`
- `completed_at`

Environment variables for backend AI analysis:

- `OPENAI_API_KEY` (required to analyze charts)
- `OPENAI_MODEL` (optional, default `gpt-5.3`)
- `OPENAI_TIMEOUT_SECONDS` (optional, default `90`)
- `OPENAI_ORGANIZATION` (optional)
- `OPENAI_PROJECT` (optional)

Trigger analysis for a stored chart:

```bash
curl -X POST http://localhost:5000/api/charts/VG/2026-02-11/vg-chart.png/analyze
```

The response includes an updated `chart.analysis` object and analysis is saved per chart.

## TradingView batch screenshot script

For `scripts/tradingview_batch_screenshots.py`, install browser automation dependencies in your Python environment:

```bash
pip install playwright playwright-stealth
playwright install chromium
```

The script now applies stealth hardening (`playwright-stealth` when available plus manual browser fingerprint tweaks), randomized human-like mouse movement, variable typing cadence, and randomized pauses to reduce automation signals that can trigger captcha prompts.

Behavior flags:
- `START_ON_LOGIN=true` (default) opens the TradingView sign-in page first; set `START_ON_LOGIN=false` to open charts directly.
- `APPLY_STEALTH_DURING_LOGIN=false` (default) defers stealth until after manual login to reduce reCAPTCHA/login stalls.
- `AUTH_FIRST_MODE=true` (default) blocks automation until the script confirms you are no longer on login/captcha pages (or you explicitly skip).
- In headed mode, Chromium launches fullscreen for easier manual captcha/login interaction.

## Deployment runbook

For a copy-paste deployment checklist, see [`DEPLOY.md`](./DEPLOY.md).

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
