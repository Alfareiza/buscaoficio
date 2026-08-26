# Buscaoficio

Full-stack starter for **Buscaoficio**: a Next.js frontend talking to a FastAPI backend, with JWT auth, a dashboard, PostgreSQL, and a typed API client generated from OpenAPI.

The repo is based on [Vinta Software’s Next.js FastAPI Template](https://github.com/vintasoftware/nextjs-fastapi-template). Domain-specific product features are not built yet; this is the production-shaped foundation (auth, CRUD, typed FE/BE contract, local Docker, AWS deployment (EC2 + RDS)).

| App | Details |
| --- | ------- |
| Backend | [`fastapi_backend/README.md`](fastapi_backend/README.md) — API, auth, Alembic, OpenAPI watcher |
| Frontend | [`nextjs-frontend/README.md`](nextjs-frontend/README.md) — UI, pages, generated client, frontend watcher |

Auth flows: [`docs/auth.md`](docs/auth.md). Setup: [`docs/get-started.md`](docs/get-started.md). Deploy: [`docs/deployment.md`](docs/deployment.md).

---

## Overview

```
Next.js (FE) ──typed client──▶ FastAPI (BE) ──asyncpg──▶ PostgreSQL
                  ▲                    │
                  │                    ▼
            openapi.json         fastapi-mail ──▶ MailHog (local)
```

| Layer | Stack |
| ----- | ----- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind + shadcn/ui, pnpm |
| Backend | FastAPI (async), Python 3.12, uv, fastapi-users (JWT), SQLAlchemy 2 + asyncpg |
| Database | PostgreSQL 17 (Docker), Alembic migrations |
| Local infra | Docker Compose (`backend`, `frontend`, `db`, `db_test`, `mailhog`) |
| Deploy | Vercel serverless (Next.js + FastAPI via `api/index.py`) — **not** containers |

What you get out of the box:

- JWT register / login / logout / password reset (email verification is not fully wired yet — see [issue #1](https://github.com/Alfareiza/buscaoficio/issues/1))
- Authenticated items CRUD with pagination
- FastAdmin at `/admin`
- Local email catcher (MailHog)
- Sentry (errors + tracing + logs) when a DSN is set

---

## The Makefile

The root [`Makefile`](Makefile) is the **single entry point** for day-to-day work. Prefer it over raw `pnpm run dev` or `uv run fastapi …`.

Those bare commands start the app **without the OpenAPI watchers**. The Makefile targets call `start.sh` on each side, which starts the app **and** the watcher. That is what keeps the frontend TypeScript client aligned with the backend API.

```bash
make help                 # list targets
```

### Host (apps on your machine, Postgres in Docker)

```bash
docker compose up -d db
make docker-migrate-db

cd fastapi_backend && uv sync && cd ..
cd nextjs-frontend && pnpm install && cd ..

make start-backend        # FastAPI on :8001 + watcher.py
make start-frontend       # Next.js on :3000 + watcher.js
```

### Docker Compose (apps in containers)

```bash
make docker-build
make docker-migrate-db
make docker-start-backend
make docker-start-frontend
```

Do not mix host-run and Docker-run casually — env URLs, hosts, and file permissions diverge.

### Why it matters

| Without Makefile | With `make start-*` / `make docker-start-*` |
| ---------------- | ------------------------------------------- |
| App only | App **plus** OpenAPI / client watchers |
| Schema drift between FE and BE | Automatic regen when API surfaces change |
| Easy to forget migrations / MailHog | Named targets for migrate, tests, shells, MailHog |

Other targets you will use often:

| Task | Command |
| ---- | ------- |
| Apply migrations | `make docker-migrate-db` |
| Generate a migration | `make docker-db-schema migration_name="add_column_x"` |
| Backend tests | `make test-backend` / `make docker-test-backend` |
| Frontend tests | `make test-frontend` / `make docker-test-frontend` |
| MailHog | `make docker-up-mailhog` |
| Test DB | `make docker-up-test-db` |
| Container shells | `make docker-backend-shell` / `make docker-frontend-shell` |

After changing SQLAlchemy models, generate and **review** the Alembic file, then migrate. Editing `models.py` does not update Postgres or the OpenAPI client by itself. Details: [`fastapi_backend/README.md`](fastapi_backend/README.md).

---

## End-to-end type safety (E2E)

This is **not** Playwright / Cypress E2E tests. Here **E2E** means the API contract is typed from FastAPI all the way into the Next.js client, so the two apps stay aligned at compile time.

```
Change BE routes / schemas
        │
        ▼
watcher.py (watchdog) → mypy + generate_openapi_schema
        │
        ▼
openapi.json (shared path)
        │
        ▼
watcher.js (chokidar) → pnpm generate-client
        │
        ▼
app/openapi-client (typed SDK)
```

1. FastAPI routes + Pydantic models produce an OpenAPI schema.
2. `@hey-api/openapi-ts` generates a TypeScript client into `nextjs-frontend/app/openapi-client`.
3. Frontend code (including server actions) calls that client instead of hand-rolled `fetch`.
4. When the schema regenerates, TypeScript fails the build if the UI is out of date.

Watchers are **dev-only**. They run via `start.sh` (Makefile / Docker `CMD`). Vercel, CI tests, and production builds do **not** run them; the generated client is committed and baked into the frontend build.

### What is watched (and what is not)

Backend `watcher.py` watches only `app/main.py`, `app/schemas.py`, and `app/routes/*.py` — **not** `models.py`. A model-only edit reloads FastAPI but does not rewrite OpenAPI or migrate the database.

### Schema file locations

| Mode | OpenAPI JSON path |
| ---- | ----------------- |
| Host (non-Docker) | `nextjs-frontend/openapi.json` |
| Docker Compose | `local-shared-data/openapi.json` (mounted in both containers) |

---

## Local ports

| Service | Host port |
| ------- | --------- |
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend API / Swagger | [http://localhost:8001](http://localhost:8001) / [docs](http://localhost:8001/docs) |
| FastAdmin | [http://localhost:8001/admin](http://localhost:8001/admin) |
| Postgres (app) | **5434** → container 5432 |
| Postgres (tests) | **5435** → container 5432 |
| MailHog SMTP / UI | 1025 / [http://localhost:8025](http://localhost:8025) |

Inside Compose, services talk to `db:5432` and `backend:8001`. Host remaps only affect processes on your machine.

---

## Environment

```bash
cp fastapi_backend/.env.example fastapi_backend/.env
cp nextjs-frontend/.env.example nextjs-frontend/.env.local
python3 -c "import secrets; print(secrets.token_hex(32))"  # run 3× for backend secret keys
```

Do not commit `.env` / `.env.local` (they may contain local keys and Sentry DSNs). Variable lists live in the app READMEs.

---

## Docs

| Doc | What it covers |
| --- | -------------- |
| [`fastapi_backend/README.md`](fastapi_backend/README.md) | API, auth, DB, Alembic, backend watcher, Vercel backend |
| [`nextjs-frontend/README.md`](nextjs-frontend/README.md) | Pages, client gen, frontend watcher, Vercel frontend |
| [`docs/get-started.md`](docs/get-started.md) | Tooling install and first run |
| [`docs/auth.md`](docs/auth.md) | Auth flows, passwords, superuser |
| [`docs/deployment.md`](docs/deployment.md) | Vercel frontend + backend |
| [`docs/additional-settings.md`](docs/additional-settings.md) | Extra configuration |
| [`docs/technology-selection.md`](docs/technology-selection.md) | Why this stack |
