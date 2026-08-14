# System Patterns

## High-level architecture
```
Next.js (FE) ──typed client──▶ FastAPI (BE) ──asyncpg──▶ PostgreSQL
                  ▲                    │
                  │                    ▼
            openapi.json         fastapi-mail ──▶ MailHog (local)
```

## OpenAPI sync pipeline (dev only)
Core of E2E type safety. Production/Vercel does **not** run watchers; generated client is baked into FE build.

```
Change BE routes/schemas
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

### Key files
| File | Role |
|------|------|
| `fastapi_backend/start.sh` | Starts FastAPI **and** `watcher.py` |
| `nextjs-frontend/start.sh` | Starts Next **and** `watcher.js` |
| `fastapi_backend/watcher.py` | Watches `main.py`, `schemas.py`, `routes/*.py` only - **not** `models.py` |
| `nextjs-frontend/watcher.js` | Watches `OPENAPI_OUTPUT_FILE`, regenerates client |
| `commands/generate_openapi_schema.py` | Writes schema; strips tag prefix from operationIds |
| `local-shared-data/openapi.json` | Shared schema path under Docker Compose |
| `nextjs-frontend/openapi.json` | Schema path for local (non-Docker) BE → FE |

### When `start.sh` runs
- Local: `make start-backend` / `make start-frontend`
- Docker: container `CMD ["./start.sh"]` via `make docker-start-*`
- **Not** on Vercel, CI tests, or production builds

### Dev workflow rule
Prefer `make start-*` / `make docker-start-*` over bare `pnpm run dev` or `uv run fastapi …`. Bare commands start the app **without** watchers → OpenAPI/client won’t auto-sync.

## Auth pattern
- fastapi-users routers mounted in `main.py` under `/api/v1/auth` + `/api/v1/users` (all
  routers moved under an `/api/v1` prefix in the Cliente/Profesional refactor; `/admin`
  and `/static` stay unprefixed).
- JWT backend; password reset uses fastapi-mail + HTML template; **email verification is not yet emailed** (token printed to log only — see GitHub issue #1)
- Routes are written explicitly in `app/routes/auth.py` (not using fastapi-users built-in router) so docstrings and summaries appear in OpenAPI docs
- Two permission levels: `current_active_user` and `current_superuser` (injected as FastAPI `Depends`); no RBAC beyond `is_superuser` flag
- Passwords hashed with Argon2 (primary) + bcrypt (fallback) via pwdlib / fastapi-users `PasswordHelper`
- To verify a password, use `PasswordHelper().verify_and_update(plain, stored_hash)` — never re-hash and compare
- Superuser creation: no CLI command; promote via SQL until a `createsuperuser` command is built
- Full auth documentation for new developers: `docs/auth.md`
- Registration has three entry points now: the plain `POST /register` (fastapi-users
  base, still present but not role-aware), and the two role-specific routes below. New
  frontend/client work should target the role-specific ones, not the plain one.

## Cliente/Profesional domain model (2026-08-14 refactor)
- `Usuario` (fastapi-users' `User`, UUID PK) is the shared identity. `Cliente` and
  `Profesional` are **not** separate entities with their own surrogate id — each has
  `usuario_id` as its own primary key (1:1 shared-PK composition, no ORM inheritance).
  This means one person can hold both roles simultaneously without duplicate identity
  rows, and there is no ambiguity about "which id" to use — it's always `usuario_id`.
- `UserCreate` (base schema, `app/schemas.py`) now requires `nombre_completo: str`. This
  applies to **every** registration path, including the plain `/register`.
- Registration: `POST /api/v1/auth/register/cliente` and `POST /api/v1/auth/register/profesional`
  each create the `Usuario` + role row in a single transaction (flush + commit, with
  `IntegrityError` → rollback + 400). This replaced the old two-step
  register-then-`POST /users/me/{cliente,profesional}` flow; those role-creation POST
  routes were removed (GET/PATCH/DELETE on existing role rows still exist).
- FastAdmin (`app/admin.py`, ~500 lines added): `ClienteAdmin`/`ProfesionalAdmin` can
  either provision a brand-new linked `Usuario` in one save, or edit the linked
  usuario's email/name/whatsapp/password from the Cliente/Profesional form.
  `UserAdmin` gets Cliente/Profesional inlines to attach a role to an existing usuario.
  Two real fastadmin bugs were worked around here (a `KeyError` in its password-hashing
  wrapper, and delete/edit silently sending `"undefined"` as the id) — both traced to
  the shared-PK column not being exposed under fastadmin's expected field name.
- Migration `c78a3f6efeb3` (`alembic_migrations/versions/`) performs the shared-PK
  change: drop old unique/FK constraints → drop `id` → create PK on `usuario_id` →
  recreate FKs. **Downgrade is only safe while `clientes`/`profesionales` are empty**
  (re-adding `id` as `NOT NULL` with no default/backfill fails once rows exist) — see
  the docstring comments in that migration file before ever downgrading in a real env.
- `app/enums.py`: richer `TipoDocumento` enum with human-readable Spanish labels.
- **Known gap**: the Next.js registration form (`components/actions/register-action.ts`,
  `lib/definitions.ts` `registerSchema`) still calls the plain `registerRegister` SDK
  function with only `email`/`password` — it was never updated for `nombre_completo` or
  the cliente/profesional split. Confirmed broken (`pnpm run tsc` fails) once the
  generated client (`app/openapi-client/*`) is regenerated from the current schema —
  tracked in GitHub issue [#7](https://github.com/Alfareiza/buscaoficio/issues/7).
  As of 2026-08-14 the committed generated client is **stale** (predates this refactor),
  which is why `pnpm run tsc` still passes today — regenerating it is what surfaces the
  break.

## Logging & Sentry pattern

### Backend
- Single logger: `from app.config import logger` (`logging.getLogger("buscaoficio")`).
- Use **f-strings** in log messages (`logger.info(f"User {user.id} logged in")`), not `%s`.
- `sentry_sdk.init()` lives in `app/main.py` **before** `app = FastAPI()`, only if
  `settings.SENTRY_DSN` is set and `"pytest" not in sys.modules`.
- `LoggingIntegration` forwards INFO+ to Sentry Logs / breadcrumbs and ERROR+
  to issues. Signals enabled: errors + tracing + logs. No profiling.
- `send_default_pii=False`. Never log tokens, passwords, or JWTs.
- Watcher / OpenAPI CLI `print()` stay as-is (dev tools, not app logs).

### Frontend (official three-runtime setup)
Next.js compiles **three isolated JS bundles**. Each needs its own `Sentry.init()`.
They cannot share one file or a `sentry.shared.ts` — a shared import can pull
Node APIs into the Edge bundle and break `proxy.ts`.

Source of truth: [Sentry Next.js manual setup](https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/).
The wizard landing page is shorter; the manual setup lists these files.

| File | Runtime | Why it exists |
|------|---------|---------------|
| `instrumentation-client.ts` | Browser | Next.js loads it automatically. Uses `NEXT_PUBLIC_SENTRY_DSN` and exports `onRouterTransitionStart`. |
| `sentry.server.config.ts` | Node.js | Server Components, Server Actions, Route Handlers. Loaded when `NEXT_RUNTIME === "nodejs"`. |
| `sentry.edge.config.ts` | Edge | `proxy.ts` (Next.js 16) runs on Edge. Loaded when `NEXT_RUNTIME === "edge"`. |
| `instrumentation.ts` | Next hook | Dynamic `import()` of server vs edge so the two bundles stay isolated. Exports `onRequestError`. |
| `app/global-error.tsx` | App Router | React render errors do **not** reach Sentry without this client boundary. |
| `withSentryConfig` in `next.config.mjs` | Build | Source maps + Webpack auto-instrumentation. |

Server and edge `init` look the same today (dsn + traces + logs). They stay
separate so a future Node-only option (`pino`, `includeLocalVariables`,
profiling) never lands in the Edge bundle.

Client looks similar but is not the same: public DSN + navigation hook.

Application code calls `Sentry.logger` / `Sentry.captureException` directly.
Do **not** add a wrapper in `lib/utils.ts`.

### Intentionally not added
- Custom frontend logger / Jest Sentry mock
- `/sentry-example-page` or test API route
- Session Replay, User Feedback, profiling
- `tunnelRoute` (optional anti-ad-block; skipped to keep config small)
- Shared `sentry.shared.ts` (defeats runtime isolation)

## FastAdmin branding
- Mounted at `/admin` in `app/main.py`. Settings come from `ADMIN_*` env vars
  (not pydantic `Settings`) and are captured when FastAdmin is imported.
- `load_dotenv()` lives in `app/__init__.py` so `.env` is in `os.environ` before
  `from fastadmin import fastapi_app`.
- Custom logos live in `app/static/` (`STATIC_DIR` from `Path(__file__).resolve().parent`
  in `app/config.py`) and are mounted at `/static`. FastAdmin uses those paths as
  `<img src>` values, so they must be browser URLs on the API origin
  (`http://localhost:8001/static/...`), not a filesystem path and not a Next.js
  `public/` file.

## CI/CD pattern

### GitHub Actions workflows (`.github/workflows/`)
| File | Trigger | Purpose |
|------|---------|---------|
| `ci.yml` | push, pull_request | FastAPI tests (own Postgres service container) + Next.js tests + Coveralls |
| `pre-commit.yml` | push, pull_request | Runs the full `.pre-commit-config.yaml` hook chain with `--all-files` |
| `migrate.yml` | push to `main` touching `fastapi_backend/alembic_migrations/**` or `alembic.ini`, or manual `workflow_dispatch` | Runs `alembic upgrade head` against production (pulls Vercel prod env, mirrors the migration step in `prod-backend-deploy.yml`) |
| `prod-backend-deploy.yml` / `prod-frontend-deploy.yml` | push to `main` (once moved into this dir — see `docs/deployment.md`) | Vercel deploy; backend step also runs `alembic upgrade head` on **every** deploy, not just migration changes |
| `release.yml` | manual `workflow_dispatch` | Draft a GitHub release from `CHANGELOG.md` |

`ci.yml` and `pre-commit.yml` no longer read `secrets.*` for backend env vars
(`DATABASE_URL`, `ACCESS_SECRET_KEY`, `CORS_ORIGINS`, etc.) — those secrets were never
set on this repo. Both now use hardcoded CI-only test values (Postgres pointed at the
job's own service container / port 5433, dummy JWT keys, `CORS_ORIGINS=["*"]`). These
are throwaway values scoped to ephemeral CI runs, not real secrets — do not read them as
a template for production config.

### `pre-commit` had never run to completion (found + fixed 2026-08-14)
Root cause: `docs/CHANGELOG.md` is a symlink to `../CHANGELOG.md`, but the root
`CHANGELOG.md` was never committed — so `check-symlinks` (the *first* hook, with
`fail_fast: true` in `.pre-commit-config.yaml`) failed on literally every run since the
initial commit, masking every hook after it. Fixing it peeled back three more
pre-existing, unrelated problems in turn:
1. **`ruff` unused import** in a migration file — one-off, fixed directly.
2. **`ruff-format` version drift**: `fastapi_backend/pyproject.toml` pins `ruff<0.2`
   (very old), but `.pre-commit-config.yaml` pins the `ruff-pre-commit` hook to
   `v0.12.2`. `uv run ruff format` and the actual pre-commit hook format code
   differently. **When reformatting to satisfy pre-commit, always run the pinned
   hook version directly** (`uvx ruff@0.12.2 format .` / `check --fix .`), not
   whatever `uv run ruff` resolves to locally.
3. **`generate-openapi-schema` / `generate-frontend-client` hooks** (local hooks, gated
   by `files:` regex on `main.py|schemas.py|pyproject.toml` and `openapi\.json$`
   respectively) — with `--all-files`, pre-commit checks those regexes against every
   tracked file, not just the current diff, so a root-level `pyproject.toml` or any
   `openapi.json` anywhere in the repo is enough to trigger them regardless of what
   changed. Running `generate-frontend-client` is what surfaces the Cliente/Profesional
   registration gap above (issue #7) — the checked-in generated client had silently
   drifted from the real schema because this hook never ran.

Also made the three `coverallsapp/github-action` steps in `ci.yml` `continue-on-error:
true` — this repo isn't registered on coveralls.io yet, so reporting fails with
`"Couldn't find a repository matching this job"` regardless of test results.

## Items pattern
- Router in `app/routes/items.py`
- Session via `Depends(get_async_session)`
- Paginated list with fastapi-pagination

## Database patterns
- Alembic is source of truth for schema; `create_db_and_tables` exists but is not the official path
- Changing `models.py` alone: FastAPI `--reload` restarts, but **watcher does not regenerate OpenAPI** and **DB does not migrate**
- After model change: also update schemas/routes if API should change; then Alembic:
  1. `make docker-db-schema migration_name="…"`
  2. Review `alembic_migrations/versions/`
  3. `make docker-migrate-db`
- Alembic uses `DATABASE_URL` (not `TEST_DATABASE_URL`)
- Inside Compose network: connect to `db:5432` / `db_test:5432` (internal ports)
- Host access uses mapped ports **5434** / **5435**
- Do not mix local-process + Docker casually (doc warns about permissions/env)

## Model change timeline
1. Save `models.py` → FastAPI reload
2. `watcher.py` skips (models not in watch regex)
3. No openapi.json / TS client update
4. DB unchanged until Alembic generate + migrate
5. If schemas/routes also change → watcher → openapi → FE client regen; DB still needs Alembic
