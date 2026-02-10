# Charts Library

A React + Flask application for saving and browsing PNG trading charts by ticker and date.

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

The React app expects the Flask API to be available at `http://localhost:5000`.

In Docker Compose watch mode, file changes under `frontend/` and `backend/` are synced into the containers so both services automatically reload. This also catches large updates such as switching Git branches while containers are running.

If you change dependencies (`frontend/package.json`, `frontend/package-lock.json`, or `backend/requirements.txt`), Compose watch automatically rebuilds the affected service.

The frontend dev server proxies `/api` requests to the backend container via `VITE_API_PROXY_TARGET=http://backend:5000`, avoiding localhost proxy errors inside Docker.

## Storage modes

The app now supports two storage modes using the same `/api/*` contract:

- `STORAGE_MODE=local` (default for Docker/local Flask backend)
  - Files are written to backend disk.
  - Docker persists uploads using a named volume: `chart_uploads:/app/storage`.
- `STORAGE_MODE=external` (for Netlify deployment)
  - Use Netlify Functions + Netlify Blobs (see next section).
  - Flask backend intentionally returns a helpful 501 in this mode; the Netlify Function is the external API implementation.

### Local mode (Docker volume persistence)

`docker-compose.yml` configures:

- `STORAGE_MODE=local`
- `LOCAL_STORAGE_DIR=/app/storage`
- named volume mount `chart_uploads:/app/storage`

This keeps uploaded images and notes across container restarts.

## Deploying frontend on Netlify + backend on Render

This is the recommended hosted setup for this repo.

### 1) Deploy backend to Render (Web Service)

Use these settings in Render:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`
- Health check path: `/api/health`
- Environment variables:
  - `STORAGE_MODE=local`
  - `LOCAL_STORAGE_DIR=/opt/render/project/src/backend/storage`
  - `FLASK_DEBUG=0`

Then add a persistent disk in Render:

- Mount path: `/opt/render/project/src/backend/storage`
- Size: 1GB (or larger)

This is required so uploaded chart files survive restarts/redeploys.

### 2) Deploy frontend to Netlify

Use these settings in Netlify:

- Base directory: repo root
- Build command: `npm --prefix frontend ci && npm --prefix frontend run build`
- Publish directory: `frontend/dist`

Set this environment variable in Netlify:

- `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`

The frontend will call the Render API directly using this value.

### Local Docker compatibility

These Netlify/Render changes do not break local Docker development:

- Docker Compose sets `STORAGE_MODE=local` and `LOCAL_STORAGE_DIR=/app/storage` for the Flask backend.
- The frontend keeps using Vite dev proxy (`VITE_API_PROXY_TARGET=http://backend:5000`) in Docker.
- `VITE_API_BASE_URL` is optional and only used when set to an absolute `http(s)` URL (recommended for Netlify).

### 3) Verify

After both deploys complete:

- Open Netlify site.
- Confirm ticker list loads.
- Upload a PNG chart.
- Confirm preview image loads.
- Confirm delete works.

## Windows notes

### Docker (recommended)

```powershell
docker compose up --build --watch
```

Then open http://localhost:8080 in your browser.

### Local dev

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

```powershell
cd frontend
npm install
npm run dev
```
