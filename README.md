# Charts Library

A React + Flask application for saving and browsing PNG trading charts by ticker and date.

## Architecture

- **Frontend:** React (Vite) app in `frontend/`.
- **Backend:** Flask API in `backend/app.py`.
- The frontend always calls the Flask API (`/api/*`).
- Storage is selected by backend `STORAGE_MODE`:
  - `local`: files on disk (`LOCAL_STORAGE_DIR`)
  - `external`: Cloudinary (free tier supported)

There is no separate Netlify Function API in this architecture.

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

## Windows notes

### Docker (recommended)

```powershell
docker compose up --build --watch
```

Then open http://localhost:8080.

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
