# Charts Library

A React + Flask application for saving and browsing PNG trading charts by ticker and date.

## Quick start

### Docker (recommended)

```bash
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend: http://localhost:5000

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
