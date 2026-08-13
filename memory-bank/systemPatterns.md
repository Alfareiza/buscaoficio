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
- fastapi-users routers mounted in `main.py` under auth prefix + `/users`
- JWT backend; password reset uses fastapi-mail + HTML template; **email verification is not yet emailed** (token printed to log only — see GitHub issue #1)
- Routes are written explicitly in `app/routes/auth.py` (not using fastapi-users built-in router) so docstrings and summaries appear in OpenAPI docs
- Two permission levels: `current_active_user` and `current_superuser` (injected as FastAPI `Depends`); no RBAC beyond `is_superuser` flag
- Passwords hashed with Argon2 (primary) + bcrypt (fallback) via pwdlib / fastapi-users `PasswordHelper`
- To verify a password, use `PasswordHelper().verify_and_update(plain, stored_hash)` — never re-hash and compare
- Superuser creation: no CLI command; promote via SQL until a `createsuperuser` command is built
- Full auth documentation for new developers: `docs/auth.md`

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
