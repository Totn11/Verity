# Verity facility dashboard

Verity is a responsive frontend prototype for facility attendance and administration. It includes a dashboard, attendance monitoring, people directory and profiles, facility map, check-in demo, reports, team permissions, login screen, and settings/audit view.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

`npm run build` runs the TypeScript check and creates the production build. The project does not currently define a separate lint or unit-test script.

## Run the verification API

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run the backend checks with `python -m unittest discover -s tests` from the `backend` directory.

The frontend development server proxies `/api` to `http://127.0.0.1:8000`. To load a trained notebook artifact, set `VERITY_SIAMESE_MODEL_PATH` to its path before starting Uvicorn. The API expects the notebook's saved `siamesemodel.h5` format; the artifact is not included in this repository. The optional `VERITY_SIAMESE_MATCH_THRESHOLD` defaults to `0.5`; calibrate it against an appropriate held-out dataset before any evaluation. Set `VERITY_ALLOWED_ORIGINS` to a comma-separated origin allowlist when the API is accessed directly from a different frontend origin, and set `VITE_API_BASE_URL` at frontend build time to that API's base URL.

## Deploy with Render and Vercel

The repository includes a Render Blueprint at `render.yaml` for the FastAPI service and Vercel configuration at `frontend/vercel.json` for the React single-page app and `/api` proxy.

1. Push the repository to a Git provider.
2. In Render, create a Blueprint from the repository and deploy the `verity-api` web service. Its health check is `/api/recognition/status`; without model weights it should report `disabled`, which is healthy and expected.
3. In Vercel, import the same repository and set the project **Root Directory** to `frontend`. Keep the detected Vite build command (`npm run build`) and output directory (`dist`).
4. The Vercel rewrite sends `/api/*` requests to `https://verity-api.onrender.com/api/*`. If Render assigns a different service hostname, change the rewrite destination in `frontend/vercel.json` and redeploy Vercel.
5. Deploy Vercel and check `/api/recognition/status` on the Vercel domain. The API proxy makes these same-origin browser requests; if you instead configure the frontend to call Render directly, set `VITE_API_BASE_URL` in Vercel and add the exact Vercel origins to Render's `VERITY_ALLOWED_ORIGINS`.

This is a deployment of the current prototype, not a production facility system: the people and attendance data remain in browser memory, and no database is provisioned or connected. Render's `starter` web service is a paid, always-on service; check current Render pricing before deploying. Do not deploy real personal or biometric data. Before production use, implement authentication, authorization, persistent data and migrations, audit controls, and an approved biometric-data policy. Model weights are intentionally not bundled or configured.

`GET /api/recognition/status` reports whether the model can be loaded. `POST /api/recognition/verify` accepts two JPEG files (`probe` and `reference`) and returns a pairwise similarity score and threshold result. Images are validated and processed in memory; they are not saved. This model compares a supplied pair and does not identify an unknown face against the people directory. The terminal only displays API readiness; it does not send camera frames to the API. There is no enrollment-image gallery or model artifact in this prototype, so terminal recognition and attendance actions remain mock-only.

## Prototype behavior

The shared in-memory demo provider seeds fictional people, attendance records, recognition events, and room-location events. A mock check-in or check-out updates those shared records so the dashboard, attendance view, person history, and facility map stay consistent for the current browser session. Refreshing the page resets the demo data.

Use the account menu's **Prototype role** selector to preview administrator and staff UI. This only hides or shows frontend controls and routes; it is not authentication or authorization.

The terminal can request an explicit browser camera preview after the user starts it. The preview does not perform facial recognition and its frames are not passed to either the mock service or the verification API. No biometric templates or camera frames are stored by this application.

## Demo limitations

All facility data is illustrative and remains in frontend memory; there is no authentication service, persistence, or live location source connected. The verification API is an isolated pairwise model integration and is not connected to attendance, identity matching, or access decisions. A recognition/access event confirms a person at that source and time only—it does not establish a current location elsewhere in the facility.

Before production use, provide server-enforced authentication and role/tenant authorization, a protected API and database, durable attendance and audit records, an authorized recognition service with consent and retention controls, and approved terminal/access-control integrations for location events. Do not treat frontend permissions as a security boundary. Do not place real face images, biometric templates, credentials, or production records in this prototype or commit them to source control.
