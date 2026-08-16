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
- Fetch a user by UUID inside a custom route with `user_manager.get(user_id)` — fastapi-users has no `get_by_id`.

### JWT refresh token rotation (branch `feature/jwt-refresh-tokens`, tracked in #9, not yet merged)
Decided 2026-08-15 after a `grill-me` design session comparing against the Hasura JWT/GraphQL best-practices article. Chose **Option B** (rotation) over a simpler single long-lived token, specifically to shrink the access-token blast radius without hurting UX.

- **Two token types, two lifetimes:**
  - Access token: JWT, 15 min (`ACCESS_TOKEN_EXPIRE_SECONDS`), returned in the login/refresh response body, sent as `Authorization: Bearer <token>`.
  - Refresh token: opaque random string, 30 days (`REFRESH_TOKEN_EXPIRE_SECONDS`), HttpOnly/Secure/SameSite=Strict cookie, **path-scoped to `/api/v1/auth/jwt/refresh` only** (never sent on other requests).
- **Fingerprint cookie (double-submit pattern, not a browser fingerprint):** a second random token, same cookie scoping as the refresh token. Both raw values must be presented together on `/auth/jwt/refresh`; both are SHA-256-hashed and compared against the stored row. A leaked refresh token alone (e.g. via logs or an XSS payload reading response bodies) is useless without the paired HttpOnly cookie the attacker's JS cannot read. This is simpler than the originally-scoped "compute a hash from user-agent + IP" approach — no fingerprint-collection code is needed on the frontend.
- **Storage:** `RefreshToken` model / `refresh_tokens` table (`app/models.py`, migration `d8c5f7a9b3e1`) stores only hashes (`refresh_token_hash`, `fingerprint_hash`), never raw tokens — `user_id`, `expires_at`, `revoked_at`, `created_ip`.
- **Service layer:** `RefreshTokenManager` (`app/refresh_token_manager.py`) — `generate_tokens`, `store_refresh_token`, `validate_refresh_token`, `rotate_refresh_token`, `detect_theft_and_revoke`, `revoke_all_user_tokens`. All DB-touching methods that mutate state call `db.commit()` internally except `store_refresh_token` (only `flush()`s — the caller commits, since it's also used mid-transaction during registration-style flows).
- **Rotation:** every successful `POST /auth/jwt/refresh` revokes the old refresh_tokens row and inserts a new one. Legitimate clients always present the newest token.
- **Theft detection:** if a client presents a refresh token whose row is already revoked (i.e. it was already rotated away — a replay), `detect_theft_and_revoke` revokes **every** active refresh token for that user and the request gets 401. This is deliberate: a replay of an old, already-superseded token is treated as a compromise signal, not a race condition to tolerate.
- **Logout:** `POST /auth/jwt/logout` revokes **all** refresh tokens for the user (every device/session dies, not just the current one) — a deliberate choice, not the minimal "revoke only this session" option.
- **Known bug (tracked in #9, not yet fixed):** `expires_in` in the login/refresh JSON response currently returns `RefreshTokenManager.REFRESH_TOKEN_LIFETIME` (30 days) instead of the access token's real lifetime (`settings.ACCESS_TOKEN_EXPIRE_SECONDS`, 15 min). Frontend (#10) must not rely on this field — decode the JWT's own `exp` claim client-side instead (unencrypted, just signed, safe to read).
- **No cleanup job yet** for expired/revoked `refresh_tokens` rows.

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

## Testing patterns
- `tests/conftest.py`'s `test_client` fixture uses `base_url="https://localhost:8001"` (not `http://`) — required so httpx's cookie jar will actually send Secure-flagged cookies (e.g. the refresh/fingerprint cookies) on subsequent requests within a test. Using `http://` makes the client silently drop them, producing confusing 401s that look like an auth bug but are actually a test-harness artifact.
- Any DB write inside a route handler needs an explicit `await db.commit()`, not just `flush()`. The test harness's `override_get_async_session` closes the session in a `finally` block right after the request completes, which rolls back anything left uncommitted — a later assertion against the same `db_session` fixture will see nothing.

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
