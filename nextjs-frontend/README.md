# Frontend - Next.js (`nextjs-frontend`)

Web UI for Buscaoficio. Consumes the FastAPI backend through a **generated typed client** derived from OpenAPI.

For the full-stack map and shared ports, see the [root README](../README.md).  
For the API, auth, and DB, see [`fastapi_backend/README.md`](../fastapi_backend/README.md).

---

## Stack

| Piece | Choice |
|-------|--------|
| Framework | Next.js **16** (App Router) |
| UI | React **19**, TypeScript |
| Styling | Tailwind CSS + **shadcn/ui** (Radix) |
| Forms | react-hook-form + **Zod** + `@hookform/resolvers` |
| API client | `@hey-api/openapi-ts` → `app/openapi-client` |
| Package manager | **pnpm** |
| Tests | Jest + Testing Library |
| Deploy | AWS EC2 (Docker image built in CI, see [`docs/deployment.md`](../docs/deployment.md)) |

---

## Pages & flows

| Route | Purpose |
|-------|---------|
| `/` | Landing / entry |
| `/login` | JWT login against backend |
| `/register` | User registration |
| `/password-recovery` | Request password reset email |
| `/password-recovery/confirm` | Set new password with token |
| `/dashboard` | Authenticated items list + delete |
| `/dashboard/add-item` | Create item |

Auth tokens are obtained from `POST /auth/jwt/login` on the backend and used by the generated client / server actions under `components/actions/`.

### Login checklist (local)

1. Backend running on **http://localhost:8001**
2. Frontend running on **http://localhost:3000**
3. DB migrated; optional MailHog if testing reset emails
4. Open `/register` → create a user → `/login` → land on `/dashboard`

If login fails, verify `API_BASE_URL` in `.env.local` and CORS/`FRONTEND_URL` on the backend.

---

## Local ports

| What | Value |
|------|-------|
| Frontend | http://localhost:**3000** |
| Backend (this repo) | http://localhost:**8001** |
| MailHog (reset emails) | http://localhost:8025 |

---

## Environment

```bash
cp .env.example .env.local
```

| Variable | Role | Local example |
|----------|------|----------------|
| `API_BASE_URL` | Backend origin for API calls | `http://localhost:8001` |
| `OPENAPI_OUTPUT_FILE` | Path to OpenAPI JSON watched/used for client gen | `openapi.json` (host) or `./shared-data/openapi.json` (Docker Compose) |

In Docker Compose, `API_BASE_URL` is set to `http://backend:8001` (service DNS), not localhost.

Production: set `API_BASE_URL` to the deployed backend URL in the on-box `nextjs-frontend/.env` (see `docs/deployment.md`).

---

## How to run

### Preferred: Makefile (starts Next **and** `watcher.js`)

From repo root:

```bash
cd nextjs-frontend && pnpm install && cd ..
make start-frontend
```

`start.sh` runs:

1. `pnpm run dev`
2. `node watcher.js` - regenerates the OpenAPI client when the schema file changes

**Do not** use only `pnpm run dev` for normal development if you expect automatic client updates when the backend API changes.

### Docker

```bash
make docker-build-frontend
make docker-start-frontend
```

Shell: `make docker-frontend-shell`.

---

## OpenAPI client generation (frontend side)

### Automatic (dev)

```
Backend writes openapi.json → watcher.js detects change → pnpm run generate-client
→ refreshes app/openapi-client/
```

Config: `openapi-ts.config.ts` (reads `OPENAPI_OUTPUT_FILE`, outputs to `app/openapi-client`, plugin `@hey-api/client-axios`).

App code should import through the app wrapper when available (`app/clientService.ts` re-exports the client).

### Manual

```bash
cd nextjs-frontend && pnpm run generate-client
# or from root docs style:
docker compose run --rm --no-deps -T frontend pnpm run generate-client
```

### Schema file locations

| Mode | File the FE watches / reads |
|------|-----------------------------|
| Host (non-Docker FE) | `nextjs-frontend/openapi.json` (backend `.env` points `OPENAPI_OUTPUT_FILE` here) |
| Docker Compose | `local-shared-data/openapi.json` mounted as `./shared-data/openapi.json` in both containers |

---

## Scripts (`package.json`)

| Script | Purpose |
|--------|---------|
| `pnpm run dev` | Next dev server (prefer via `make start-frontend`) |
| `pnpm run build` | Production build |
| `pnpm run start` | Serve production build |
| `pnpm run generate-client` | Regenerate OpenAPI TS client |
| `pnpm run test` | Jest |
| `pnpm run coverage` | Jest with coverage |
| `pnpm run lint` / `lint:fix` | ESLint |
| `pnpm run prettier` | Format |
| `pnpm run tsc` | Typecheck |

Root Makefile wrappers:

```bash
make start-frontend
make test-frontend
make docker-start-frontend
make docker-test-frontend
```

---

## UI & forms conventions

- Prefer existing **shadcn/ui** primitives under `components/ui/`.
- Forms: Zod schema + react-hook-form (see login/register/password-recovery).
- Server actions for API mutations live under `components/actions/`.
- Keep calling the **generated** client rather than hand-rolled `fetch` to preserve E2E types.

---

## Deploy - frontend perspective

Production is AWS (EC2 + Docker + Caddy), not Vercel. CI builds `Dockerfile.prod` and pushes to ECR; the box pulls and runs it. `FRONTEND_URL` must be set in the on-box env — Route Handler redirects behind the reverse proxy resolve to the container bind address otherwise. Full picture: [`docs/deployment.md`](../docs/deployment.md).

The build uses the generated `app/openapi-client` already in the tree (no backend/watcher needed at build time).

---

## Useful paths

```
nextjs-frontend/
├── app/
│   ├── login/
│   ├── register/
│   ├── password-recovery/
│   ├── dashboard/
│   ├── openapi-client/     # GENERATED - do not hand-edit
│   ├── clientService.ts
│   └── layout.tsx
├── components/
│   ├── actions/            # Server actions calling the API
│   └── ui/                 # shadcn components
├── openapi-ts.config.ts
├── watcher.js              # Dev: regenerate client on schema change
├── start.sh                # Dev: Next + watcher
└── __tests__/
```

---

## Commands quick reference

| Task | Command |
|------|---------|
| Start FE + watcher | `make start-frontend` |
| Start FE (Docker) | `make docker-start-frontend` |
| Generate client | `pnpm run generate-client` |
| Tests | `make test-frontend` / `make docker-test-frontend` |
| Lint | `pnpm run lint` |
| Typecheck | `pnpm run tsc` |
| Shell | `make docker-frontend-shell` |
