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

## Frontend proxy (middleware) config
⚠️ **Critical:** `nextjs-frontend/proxy.ts` config.matcher **must be a literal array**, not a variable. If it references a const (e.g., `matcher: loginRequiredPaths`), Next.js can't parse it statically → proxy applies globally instead of the intended routes → causes redirect loops on non-protected paths. Always inline: `matcher: ["/dashboard/:path*"]`.

## Auth pattern
- fastapi-users routers mounted in `main.py` under auth prefix + `/users`
- **Login/registration is passwordless email OTP, not password auth** — see
  "Passwordless OTP auth pattern" below. Password-based `/jwt/login`,
  `/register`, `/register/cliente`, `/register/profesional` were removed
  2026-08-18; `/forgot-password`/`/reset-password`/`/request-verify-token`/
  `/verify` still exist but are now vestigial (see that section).
- JWT backend (access + rotating refresh tokens, see below) is shared by
  every login path via `build_session_response()` — it doesn't care whether
  the caller was OTP verify or (formerly) password login.
- Routes are written explicitly in `app/routes/auth.py` (not using fastapi-users built-in router) so docstrings and summaries appear in OpenAPI docs
- Two permission levels: `current_active_user` and `current_superuser` (injected as FastAPI `Depends`); no RBAC beyond `is_superuser` flag
- Passwords hashed with Argon2 (primary) + bcrypt (fallback) via pwdlib / fastapi-users `PasswordHelper`
- To verify a password, use `PasswordHelper().verify_and_update(plain, stored_hash)` — never re-hash and compare
- Superuser creation: no CLI command; create a user via the app's OTP sign-up flow or FastAdmin, then promote via SQL until a `createsuperuser` command is built
- Full auth documentation for new developers: `docs/auth.md`
- Fetch a user by UUID inside a custom route with `user_manager.get(user_id)` — fastapi-users has no `get_by_id`.

## Passwordless OTP auth pattern (primary login/registration flow, since 2026-08-18)
Login and signup are the same screen/flow — the backend doesn't know which the user "meant" until the OTP is verified. Full design writeup: `docs/auth.md` § "0 · Passwordless login".

- **Flow:** `POST /otp/request` (email → 6-digit code, always 202, anti-enumeration) → `POST /otp/verify` (email+code → either logs an existing user in, or returns a short-lived signed `registration_token`) → for a brand-new email, `POST /register/cliente/otp` or `/register/profesional/otp` (registration_token + profile fields → creates the account atomically and logs in).
- **No account exists until registration completes.** `/otp/request`/`/otp/verify` never write a `usuarios` row for a new email — only the signed `registration_token` (`OtpManager.issue_registration_token`, ~15 min). This means an abandoned signup (closed tab after seeing the code) never leaves a ghost account. Deliberate design choice, not an oversight.
- **`OtpManager` (`app/otp_manager.py`)** — modeled directly on `RefreshTokenManager`'s shape. Codes are SHA-256 hashed, never stored raw, in the `email_otps` table (migration `a067ad066d81`). 10-minute expiry (`OTP_CODE_EXPIRE_SECONDS`), max 5 verify attempts, 30s resend cooldown. Like `refresh_tokens`, **rows are never purged** — same known cleanup gap, now duplicated across two tables.
- **OTP-created accounts get a random, never-disclosed password** (`secrets.token_urlsafe(32)`, hashed normally) purely because fastapi-users' schema requires `hashed_password` to be non-null — it can never actually be used to log in, since nobody knows it (not even the user). `is_verified` is set `true` immediately, since entering the code already proves mailbox ownership.
- **Session issuance is shared code**, not duplicated per flow: `build_session_response()` (`app/refresh_token_manager.py`) is called by OTP verify (existing user) and both OTP-backed registration routes. This is the same function password login used to call — removing password login didn't touch this shared path at all.
- **Frontend:** `components/actions/otp-auth-action.ts` (Server Actions: `requestOtpAction`, `verifyOtpAction`, `registerClienteOtpAction`, `registerProfesionalOtpAction`) and `components/auth/AuthCard.tsx` (single client component driving a 4-step flow: `email → otp → onboarding-name → onboarding-role`, keyed by local `useState`, not a wizard library). `AuthCard` takes `mode: "page" | "modal"` (modal calls an `onSuccess` callback instead of `router.push`) and `intent?: "login" | "register"` (controls subtitle copy + the bottom toggle link only — the underlying flow is identical either way, since OTP doesn't know login vs. signup until verify).
- **`/login` and `/register` share `app/(auth)/layout.tsx`** (a Next.js route group — doesn't affect the URL). The background/card frame lives in the layout, not each page, so navigating between the two via `AuthCard`'s toggle link is a soft RSC navigation, not a full page reload — confirmed via network trace (`GET /register?_rsc=...`). This is the mechanism behind the "instant" login↔register toggle feel.
- **Testing pattern:** mock `app.routes.auth.send_otp_code_email` with an autouse `mocker.patch(...)` fixture (`mock_send_otp_email`), then read the real code back via `mock_send_otp_email.call_args[0][1]` after calling `/otp/request` — see `tests/routes/test_auth_otp.py`. Other test files that need a logged-in session but aren't testing OTP itself (e.g. `test_auth_refresh.py`) reuse this same pattern as their login helper instead of hitting a login route directly.

### JWT refresh token rotation (backend, #9 — merged to `main` via PR #11)
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
- **`expires_in` bug: fixed** (on branch `feature/jwt-frontend-refresh`, folded into #10 rather than shipped standalone). Both `/jwt/login` and `/jwt/refresh` now return `settings.ACCESS_TOKEN_EXPIRE_SECONDS`; previously returned the refresh token's 30-day lifetime. 2 regression tests added. (`/jwt/login` itself was removed 2026-08-18 — see "Passwordless OTP auth pattern" above — but the fix lives on in `build_session_response()`, which every surviving login path calls.)
- **No cleanup job yet** for expired/revoked `refresh_tokens` rows (nor for `email_otps`, the OTP equivalent — same gap, two tables).

## Frontend auth pattern (#10 — merged to `main` via PR #12)

The current frontend is **Server Actions + Edge middleware based** — every backend call is server-to-server (from the Next.js server, not the browser), which changes how refresh tokens have to be handled compared to a typical SPA. `API_BASE_URL` deliberately has no `NEXT_PUBLIC_` prefix, confirming the browser never calls FastAPI directly today. **This is a factual description of the current code, not a locked-in decision** — see `activeContext.md` for an open, unresolved discussion about whether to keep this, move to a full SPA, or a hybrid (server-mediated auth + client-side CRUD/live features).

- **The cookie-forwarding problem:** a server-to-server fetch's `Set-Cookie` response headers land on the Next.js server, not the browser — they must be explicitly re-applied on the Next.js server's own response. `lib/auth-cookies.ts` centralizes this: `forwardAuthCookies`, `setAccessTokenCookie`, `clearAuthCookies`, `decodeJwtExpiryMs`. Uses a structural `CookieWriter` interface (`set`/`delete`) rather than importing a concrete type, since it's called from two runtimes with different-but-compatible cookie APIs: `next/headers`'s `cookies()` (Server Actions) and `NextResponse.cookies` (middleware).
- **Silent refresh via `proxy.ts`:** no persistent client-side refresh timer. `proxy.ts` runs on every `/dashboard/:path*` request (matches Server Action POSTs to those routes too), decodes the access token's `exp`, and if expired or within a 2-minute buffer, refreshes server-to-server against FastAPI — manually forwarding `refreshToken`/`fingerprintToken` as a `Cookie` header (server-to-server calls don't auto-attach the browser's cookies). On success, forwards the new cookies onto the outgoing response. On failure (including theft-detection revocation), clears all cookies and redirects to `/login`.
- **Reactive fallback in Server Actions:** `items-action.ts` checks each result with `isUnauthorizedError()` (`lib/api-errors.ts`, handles both a top-level `status` and Axios's nested `response.status` shape) — catches a token revoked between the middleware's check and the actual call.
- **Cross-tab logout needs no active sync code:** unlike `localStorage`/in-memory SPA token storage, cookies are already shared by the browser across tabs for the same origin — there's no separate client-side state to desync. The only gap (a tab with stale "logged in" UI) is caught on its next navigation/action by `proxy.ts` or the reactive fallback above. Deliberately did not add `BroadcastChannel`/`storage`-event sync — it would solve a problem this architecture doesn't have.
- **Page protection = `proxy.ts`'s `matcher`, nothing else.** There is no per-page or per-layout auth check anywhere in the app — `app/dashboard/layout.tsx` is UI chrome only. `proxy.ts` runs (and gates access) only on routes matching `config.matcher`, currently `["/dashboard/:path*"]`. A route outside that pattern is fully public, silently, with no error or warning. **To protect a new page:** put it under `/dashboard/...` (automatic) or add its path to `matcher` if it can't live there. This is a common trap for a future agent adding a page — it's easy to assume auth is checked globally or per-layout when it's actually one middleware config array.
- Full write-up: `docs/auth.md` § "How page protection actually works — and how to add a new protected page".

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
- Frontend: Jest's default `jsdom` environment lacks the `Request`/`Response` Web APIs that `next/server`'s `NextRequest` needs — any test file that imports `NextRequest` (e.g. `proxy.test.ts`) needs `/** @jest-environment node */` at the top.
- Frontend: Next.js `redirect()` throws internally in production, but a Jest mock of it does not — code depending on `redirect()` halting execution needs an explicit `return redirect(...)`, otherwise execution falls through under test (can end up calling a downstream function with an undefined token, e.g. `logout-action.ts`/`items-action.ts`).
- Frontend: **`jest.mock("...")` string arguments must use relative paths, not the `@/` alias.** Next's SWC transform rewrites `@/`-aliased specifiers in real `import` statements at parse time, but not inside a `jest.mock()` call, so `jest.mock("@/components/x", ...)` fails to resolve while `jest.mock("../components/x", ...)` works. Direct (non-mocked) imports of the module under test can still use `@/`. Every test file in this repo already follows this convention — found the hard way while adding `AuthCard.test.tsx`/`loginPage.test.tsx`.
- Backend: after an HTTP call through `test_client`, don't call `await db_session.refresh(some_earlier_object)` — `conftest.py`'s `override_get_user_db` closes `db_session` in a `finally` block after every request that resolves `get_user_db` (which most authenticated routes do), so the object is no longer in that session's identity map and `.refresh()` raises `InvalidRequestError: Instance ... is not persistent`. Re-query fresh instead: `(await db_session.execute(select(Model).where(...))).scalar_one()`. `db_session.execute(...)` itself is fine post-request (the session silently reopens); it's specifically `.refresh()` on a stale object that breaks.

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
