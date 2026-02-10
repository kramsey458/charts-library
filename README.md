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


## Ticker autocomplete + validation data

The upload form now uses a locally stored ticker catalog for autocomplete and soft validation (warning only, upload is still allowed).

- Catalog file: `backend/data/valid_tickers.json`
- API endpoint: `GET /api/valid-tickers`
- Scraper script (no paid API):

```bash
python backend/scripts/scrape_tickers.py
```

The scraper pulls public exchange symbol-directory pages (US, Canada, and OTC) and writes the merged list locally.

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

## Netlify external mode (Netlify Blobs)

This repo includes a Netlify Function API at `netlify/functions/api.mjs` that mirrors the Flask endpoints:

- `GET /api/health`
- `GET /api/tickers`
- `GET /api/charts/:ticker`
- `POST /api/charts` (multipart form upload)
- `DELETE /api/charts/:ticker/:date/:filename`
- `GET /api/chart-file/:ticker/:date/:filename`

`netlify.toml` routes `/api/*` to that function, and the function stores image binaries + chart metadata in Netlify Blobs.

### Deploying to Netlify

1. Build command: already set in `netlify.toml` (`npm --prefix frontend ci && npm --prefix frontend run build`)
2. Publish directory: `frontend/dist`
3. Functions directory: `netlify/functions`
4. Set env vars in Netlify:
   - `STORAGE_MODE=external`
   - optional `NETLIFY_BLOBS_STORE=chart-vault` (or your preferred store name)

With this setup, local Docker uses persistent local volume storage, while Netlify uses persistent blob storage.

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
