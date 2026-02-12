# Deployment Runbook (Cloudinary + Render + Netlify)

Use this checklist to deploy **Charts Library** with:

- **Cloudinary** for image storage
- **Render** for the Flask backend
- **Netlify** for the React frontend

---

## 1) Cloudinary setup

1. Log in to Cloudinary.
2. Create or select your product environment.
3. Copy these values:
   - `CLOUDINARY_CLOUD_NAME`
   - `CLOUDINARY_API_KEY`
   - `CLOUDINARY_API_SECRET`
4. Choose a folder name (recommended):
   - `charts-library`

---

## 2) Deploy backend on Render

Create a **Web Service** in Render connected to this repository.

Use the following settings:

- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`
- **Health Check Path:** `/api/health`

Set environment variables:

```bash
STORAGE_MODE=external
CLOUDINARY_CLOUD_NAME=YOUR_VALUE
CLOUDINARY_API_KEY=YOUR_VALUE
CLOUDINARY_API_SECRET=YOUR_VALUE
CLOUDINARY_FOLDER=charts-library
```

After deploy, verify backend health:

```text
https://YOUR-RENDER-SERVICE.onrender.com/api/health
```

Expected JSON should include:

- `"status": "ok"`
- `"storage_mode": "external"`
- `"provider": "cloudinary"`

---

## 3) Deploy frontend on Netlify

Create/import a Netlify site from this repository.

Use the following build settings:

- **Base directory:** repository root
- **Build command:** `npm --prefix frontend ci && npm --prefix frontend run build`
- **Publish directory:** `frontend/dist`

Set Netlify environment variable:

```bash
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Then deploy.

---

## 4) Verification checklist

After both services are live:

1. Open your Netlify site URL.
2. Confirm the ticker list loads.
3. Upload a `.png` chart.
4. Confirm image preview loads.
5. Confirm delete works.

Optional API checks:

- `GET https://YOUR-RENDER-SERVICE.onrender.com/api/health`
- `GET https://YOUR-RENDER-SERVICE.onrender.com/api/tickers`

---

## 5) Troubleshooting

### Frontend loads but API calls fail

- Confirm `VITE_API_BASE_URL` is set in Netlify.
- Confirm it exactly matches your Render URL (`https://...onrender.com`).
- Redeploy Netlify after changing env vars.

### Backend reports missing Cloudinary config

- Confirm `STORAGE_MODE=external`.
- Confirm all Cloudinary env vars are set on Render.
- Redeploy Render after changing env vars.

### Data not persisting on Render

- Use `STORAGE_MODE=external` for Cloudinary-backed persistence.
