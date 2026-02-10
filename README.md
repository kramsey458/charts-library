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
