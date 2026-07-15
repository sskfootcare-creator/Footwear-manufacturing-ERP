# Copilot Instructions for SSK Footcare ERP

- This repo is a Windows-focused monorepo with a FastAPI backend in `backend/` and a Create React App frontend in `frontend/`.
- The main backend entrypoint is `backend/server.py`; most API routes are defined in this single file under `api = APIRouter(prefix="/api")` and then mounted with `app.include_router(api)`.
- Authentication is handled by `backend/auth.py`: JWT access tokens are stored in secure cookies when possible, with `Authorization: Bearer` as a fallback. The backend also seeds admin users at startup via `seed_admin(db)`.
- Local image uploads are stored under `backend/uploads/images/` and served both at `/api/uploads/...` and `/uploads/...`. Relative URLs are required for local dev so browser origins remain consistent.
- The frontend uses CRACO and path alias `@/*` configured in `frontend/jsconfig.json` and `frontend/craco.config.js`. Use alias imports for `src/` files instead of deep relative paths.
- `frontend/src/App.js` defines the route structure and protected routes for authenticated users. The app expects a workspace value in `localStorage` and redirects to `/select-workspace` if it is missing.
- CORS is configured in `backend/server.py` to allow `localhost:3000` and the env-driven `FRONTEND_URL`.
- `backend/requirements.txt` is the source of Python dependencies; `frontend/package.json` contains React/CRA scripts.

## Local Development

- Start the app from repo root with `.
un_dev.ps1` or `.ackend\.venv\Scripts\python.exe -m uvicorn server:app --port 8000 --reload` plus `npm start` in `frontend/`.
- The provided `start_dev.ps1` script kills ports `27017`, `8000`, and `3000`, then launches local MongoDB, backend, and frontend together.
- Backend environment configuration is loaded from `backend/.env`. Required variables include `MONGO_URL`, `DB_NAME`, and `JWT_SECRET`.
- `frontend` dev server runs on `http://localhost:3000`; backend runs on `http://localhost:8000` with API routes under `/api`.

## Testing and Seed Data

- Backend tests live in `backend/tests/` and use `pytest` with xdist. `backend/pytest.ini` sets `addopts = -n 2 --dist loadscope`; do not change that for this repo.
- Demo data can be seeded with `backend/seed_demo.py`; it is idempotent and supports `--reset` to wipe demo records.
- `backend/auth.py` seeds a test admin account with `admin@sskfootcare.com` / `Admin@123` and also seeds the env-defined admin credentials.

## Important Project Conventions

- Keep backend endpoint logic in `backend/server.py`; this repo does not split routes across many routers by default.
- Use `ObjectId` conversions carefully: `backend/server.py` uses `oid(v)` helpers and `stringify(doc)` to normalize Mongo documents.
- Preserve the `@app.on_event("startup")` ordering in `backend/server.py` because startup tasks create indexes, build auth dependency, and seed users.
- Frontend uses React Query and `react-router-dom` v7. Avoid untyped route changes in `App.js` and preserve the protected-route pattern.
- For image/file upload handling, prefer backend `/api/upload/image` and the `uploads/images/<uuid>` local storage pattern.

## When editing

- Search `backend/server.py` for the relevant `api.post`, `api.get`, `api.patch`, and `api.delete` endpoints before adding new routes.
- If API path changes are needed, keep `/api` prefix consistent with frontend requests.
- Use `backend/auth.py` utilities for password hashing, token creation, cookie management, and `require_roles` authorization.
- Avoid changing `pytest.ini` addopts or xdist settings unless the test suite is explicitly being redesigned.
