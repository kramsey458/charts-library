# Pipeline Manual QA Checklist

## Hosted flow (Netlify/Render style)
1. Open **Pipeline** tab.
2. Upload `.txt` ticker file and verify parsed valid/invalid rows.
3. Create job, start pipeline, and confirm `awaiting_login` state.
4. Click **Open Login Session**, complete Google/TradingView auth, then click resume.
5. Confirm running progress updates until upload decision gate appears.
6. Adjust policy and per-ticker overrides, upload approved charts.
7. Verify final job state and downloadable report JSON.

## Login handoff checks
- Confirm login URL expires after TTL and resume returns `SESSION_EXPIRED`.
- Confirm owner mismatch cannot open login session (`FORBIDDEN`).
- Confirm resume before auth returns `LOGIN_NOT_CONFIRMED`.

## Cancel + retry checks
- Cancel during `awaiting_login` and ensure terminal `cancelled` state.
- Start new job and repeat flow to completion.
