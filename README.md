# Verity facility dashboard

Verity is a responsive frontend prototype for facility attendance and administration. It includes a dashboard, attendance monitoring, people directory and profiles, facility map, check-in demo, reports, team permissions, backend-connected sign-in, and settings/audit view.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

`npm run build` runs the TypeScript check and creates the production build. The project does not currently define a separate lint or unit-test script.

Set `VITE_DATA_SOURCE=api` before starting the frontend to load people, rooms, and attendance from `/api/v1`; the default is `demo`, which retains the in-memory sample provider. Keep the frontend and API on the same origin or use the configured `/api` proxy so the session cookie is sent correctly. API mode requires a signed-in account and database-backed facility data. The API does not provide recognition or live-location events; map occupancy is derived from attendance events and uses illustrative floor-plan geometry.

## Run the verification API

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Install backend test dependencies with `python -m pip install -r requirements-dev.txt`, then run `python -m pytest` from the `backend` directory.

Configure `DATABASE_URL` with a PostgreSQL async connection URL before starting the backend, for example:

```bash
export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/verity'
```

The database layer does not create tables automatically. After adding models and a migration, create and apply migrations from `backend/` with `alembic revision --autogenerate -m "describe schema"` followed by `alembic upgrade head`. `GET /api/health` reports API health and returns `"database": "unavailable"` if the database is not configured or cannot be reached.

Each API response includes an `X-Request-Id` UUID generated for that request. Successful person and attendance mutations, plus login and logout attempts, write before/after snapshots to `audit_events` in the same transaction as the business operation. A PostgreSQL trigger rejects `UPDATE` and `DELETE` against that table; apply the latest migration with `alembic upgrade head`.

Facility persistence is accessed through asynchronous repository interfaces in `backend/app/repositories/`. `get_repositories()` provides SQLAlchemy-backed implementations when `DATABASE_URL` is configured and shared in-memory repositories otherwise. Attendance event recording is idempotent by source and source-event ID; current occupancy is calculated from each person's latest event.

The versioned facility API is rooted at `/api/v1` and uses server-enforced roles:

| Route | Access | Description |
| --- | --- | --- |
| `GET /people?q=&status=&limit=&cursor=` | admin, staff | Search and cursor-page people |
| `GET /people/{person_id}` | admin, staff | Get a person |
| `POST /people`, `PATCH /people/{person_id}`, `PUT /people/{person_id}` | admin | Create or update people |
| `GET /rooms`, `GET /rooms/{room_id}` | admin, staff | Cursor-page rooms or get a room |
| `GET /attendance?person_id=&from=&to=&limit=&cursor=` | admin, staff | Filter and cursor-page events |
| `POST /attendance/check-in`, `POST /attendance/check-out` | admin, staff | Record a manual attendance event |
| `GET /reports/attendance-summary?from=&to=&limit=&cursor=` | admin, staff | Daily check-in/out counts grouped by room |

Collection responses use `{"items": [...], "next_cursor": "..."}`; cursor values are opaque and should be passed back unchanged. Timestamp filters and event timestamps must include a timezone and are normalized to UTC. Check-in/out accept an optional `Idempotency-Key` header, which is stored as the event's source-event ID.

Create the first database-backed account after setting `DATABASE_URL` and applying migrations:

```bash
cd backend
python -m app.cli create-user --email operator@example.com --role admin
```

The CLI securely prompts for and confirms a password, then stores its Argon2 hash. Sign-in sessions are opaque random tokens; only their SHA-256 hashes are stored, and logout revokes the session in the database. Cookies are HttpOnly, Secure, SameSite=Lax, and expire after eight hours. Sign-in is rate-limited to five failures per IP hash in a 15-minute window.

The frontend development server proxies `/api` to `http://127.0.0.1:8000`. Keep the frontend and API on the same origin or behind a same-origin `/api` proxy so the session cookie is sent correctly. To load a trained notebook artifact, set `VERITY_SIAMESE_MODEL_PATH` to its path before starting Uvicorn. The API expects the notebook's saved `siamesemodel.h5` format; the artifact is not included in this repository. The optional `VERITY_SIAMESE_MATCH_THRESHOLD` defaults to `0.5`; calibrate it against an appropriate held-out dataset before any evaluation.

## Deploy with Render and Vercel

The repository includes a Render Blueprint at `render.yaml` for the FastAPI service and Vercel configuration at `frontend/vercel.json` for the React single-page app and `/api` proxy.

1. Push the repository to a Git provider.
2. In Render, create a Blueprint from the repository and deploy the `verity-api` web service. Configure `DATABASE_URL` for the PostgreSQL database, then create the first administrator with the CLI. Its health check is `/api/recognition/status`; without model weights it should report `disabled`, which is healthy and expected.
3. In Vercel, import the same repository and set the project **Root Directory** to `frontend`. Keep the detected Vite build command (`npm run build`) and output directory (`dist`).
4. The Vercel rewrite sends `/api/*` requests to `https://verity-api.onrender.com/api/*`. If Render assigns a different service hostname, change the rewrite destination in `frontend/vercel.json` and redeploy Vercel.
5. Deploy Vercel and check `/api/recognition/status` on the Vercel domain. The API proxy makes these same-origin browser requests, including sign-in and session-cookie requests.

This is a deployment of the current prototype: authentication, sessions, audit events, and the initial facility schema use PostgreSQL, and `/api/v1` applies server-side role authorization. The frontend's facility views still use illustrative in-memory data and are not yet wired to those endpoints. Render's `starter` web service is a paid, always-on service; check current Render pricing before deploying. Do not deploy real personal or biometric data. Before production use, complete deployment-specific session and abuse controls, operational data retention and backup policies, and an approved biometric-data policy. Model weights are intentionally not bundled or configured.

`GET /api/recognition/status` reports whether the model can be loaded. `POST /api/recognition/verify` accepts two JPEG files (`probe` and `reference`) and returns a pairwise similarity score and threshold result. Images are validated and processed in memory; they are not saved. This model compares a supplied pair and does not identify an unknown face against the people directory. The terminal only displays API readiness; it does not send camera frames to the API. There is no enrollment-image gallery or model artifact in this prototype, so terminal recognition and attendance actions remain mock-only.

## Prototype behavior

The shared in-memory demo provider seeds fictional people, attendance records, recognition events, and room-location events. A mock check-in or check-out updates those shared records so the dashboard, attendance view, person history, and facility map stay consistent for the current browser session. Refreshing the page resets the demo data.

Use the account menu's **Prototype role** selector to preview administrator and staff UI. This only hides or shows frontend controls and routes; it is not authentication or authorization. The `/api/v1` backend checks the signed-in user's database role independently.

The terminal can request an explicit browser camera preview after the user starts it. The preview does not perform facial recognition and its frames are not passed to either the mock service or the verification API. No biometric templates or camera frames are stored by this application.

## Demo limitations

In demo mode, facility data remains illustrative and in browser memory. API mode uses persistent people, rooms, and attendance endpoints, but has no live location source. API room associations are derived from attendance records and displayed on illustrative floor-plan geometry. The verification API is an isolated pairwise model integration and is not connected to attendance, identity matching, or access decisions. A recognition/access event confirms a person at that source and time only—it does not establish a current location elsewhere in the facility.

Before production use, provide tenant-level data isolation, durable retention and backup operations, an authorized recognition service with consent and retention controls, and approved terminal/access-control integrations for location events. Do not treat frontend permissions as a security boundary. Do not place real face images, biometric templates, credentials, or production records in this prototype or commit them to source control.
