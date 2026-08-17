# Active Context

## Current focus
- JWT session hardening: backend refresh token rotation
  ([#9](https://github.com/Alfareiza/buscaoficio/issues/9)) is **merged to
  `main`** via PR #11 (commit `0a8376b`). Frontend side
  ([#10](https://github.com/Alfareiza/buscaoficio/issues/10) — cookie
  forwarding, silent refresh, reactive 401 fallback) is **fully implemented
  and tested on branch `feature/jwt-frontend-refresh`, intentionally left
  uncommitted** pending explicit go-ahead.
- **Open architecture question, unresolved:** whether to keep the current
  server-mediated frontend (Server Actions + Edge middleware — what #10 was
  built on), move toward a client-side SPA calling FastAPI directly, or a
  hybrid (server-mediated auth + client-side CRUD/live features once a short
  token is available). Surfaced when the user pushed back on the "Server
  Actions, not a client SPA" characterization and described the product's
  intended client-server usage pattern (cliente/profesional actions
  eventually calling the API directly). Not decided — user wants to keep
  talking it through (e.g. by walking a concrete future feature, like a
  service request with live status, through each option) before committing.
  This choice determines whether the already-built #10 work is the right
  long-term foundation or needs rework. See Active decisions below for the
  provisional lean.
- FastAdmin branding (site name + logo) is wired; auth gaps (email
  verification, #1) are still open behind the JWT work above.

## Recent changes
- **JWT refresh token rotation frontend (#10, branch
  `feature/jwt-frontend-refresh`, based on merged `main`, not committed):**
  - `lib/auth-cookies.ts` (new): `forwardAuthCookies`, `setAccessTokenCookie`,
    `clearAuthCookies`, `decodeJwtExpiryMs` — re-applies backend `Set-Cookie`
    headers onto the Next.js server's own response, since server-to-server
    fetches never expose them to the browser directly. Uses a structural
    `CookieWriter` interface so the same helpers work from both
    `next/headers`' `cookies()` (Server Actions) and `NextResponse.cookies`
    (middleware).
  - `lib/api-errors.ts` (new): `isUnauthorizedError()` — detects a 401 from
    either the top-level or Axios-nested `response.status` shape.
  - `proxy.ts` (rewritten): decodes the access token's `exp` claim before
    every `/dashboard/:path*` request; if expired or within 2 minutes of
    expiring, refreshes server-to-server against
    `${API_BASE_URL}/api/v1/auth/jwt/refresh` (manually forwarding
    `refreshToken`/`fingerprintToken` as a `Cookie` header), forwards the new
    cookies to the browser, and redirects to `/login` (clearing cookies) on
    any failure. This is the app's silent-refresh mechanism — there is no
    client-side refresh timer.
  - `login-action.ts` / `logout-action.ts`: now use the shared cookie
    helpers — login forwards all three cookies from the backend response;
    logout clears all three (previously only cleared `accessToken`).
  - `items-action.ts`: each backend call checks `isUnauthorizedError()` as a
    reactive fallback — if a token is revoked between the middleware's check
    and the actual call, the action clears cookies and redirects instead of
    surfacing a generic error.
  - Fixed the `expires_in` bug (folded into this branch per user's choice
    rather than a standalone fix): both `/jwt/login` and `/jwt/refresh` now
    return `settings.ACCESS_TOKEN_EXPIRE_SECONDS`, not the refresh token's
    30-day lifetime. 2 new backend regression tests.
  - Decided **not** to implement `BroadcastChannel`/`storage`-event cross-tab
    sync — cookies are already shared natively across tabs for the same
    origin, so there's no separate client-side session state that could go
    stale per tab. Documented in `docs/auth.md` instead of built.
  - Tests: 104/104 backend, all frontend suites green (12 test files,
    including new `auth-cookies.test.ts`, `api-errors.test.ts`,
    `logout.test.tsx`, `proxy.test.ts`). `proxy.test.ts` needs
    `/** @jest-environment node */` — jsdom lacks the `Request`/`Response`
    APIs `next/server`'s `NextRequest` needs.
  - `docs/auth.md` extended with a "Frontend: cookie forwarding & silent
    refresh" section and updated FAQ answers — see docs section below.
- **JWT refresh token rotation (backend, #9 — merged via PR #11):**
  - New `RefreshToken` model (`app/models.py`) + table `refresh_tokens`
    (migration `d8c5f7a9b3e1`): hash of refresh token, hash of a paired
    fingerprint token, expiry, revocation timestamp, issuing IP.
  - New `RefreshTokenManager` (`app/refresh_token_manager.py`): generate,
    store, validate, rotate, theft-detect, revoke-all.
  - `POST /auth/jwt/login` and `POST /auth/jwt/refresh` now set two
    HttpOnly/Secure/SameSite=Strict cookies (`refreshToken`,
    `fingerprintToken`), path-scoped to `/api/v1/auth/jwt/refresh` only.
    This is a **double-submit cookie pattern**, not a computed browser
    fingerprint (no user-agent/IP hashing) — simpler than originally scoped
    in the issue.
  - `POST /auth/jwt/refresh` (new endpoint) rotates the refresh token on
    every call; replaying an already-rotated token revokes **all** refresh
    tokens for that user (theft detection).
  - `POST /auth/jwt/logout` now revokes all refresh tokens for the user
    (kills every device/session, not just the current one) — deliberate
    choice, see Active decisions.
  - `ACCESS_TOKEN_EXPIRE_SECONDS` default lowered 3600 → **900** (15 min).
    New `REFRESH_TOKEN_EXPIRE_SECONDS` = **2592000** (30 days).
  - 27 new tests (`tests/test_refresh_tokens.py`,
    `tests/routes/test_auth_refresh.py`); full backend suite 102/102 green
    at merge time (now 104/104 with the #10 branch's `expires_in` fix tests).
  - `docs/auth.md` rewritten with a full "Refresh tokens & rotation"
    section plus FAQ entries on token-expiry detection and closing the
    browser without logging out.
  - Issues #8 (parent/architecture decision), #9, #10 all rewritten to
    reflect the actual implementation (Option B — refresh rotation — was
    chosen over Option A — single long-lived token — deliberately, to keep
    the access-token blast radius small without hurting UX).
  - Issue #10 was further **rewritten a second time** before implementation
    started: its original text assumed client-side JWT decoding /
    BroadcastChannel / direct browser→backend calls, which don't match this
    app's actual Server Actions + Edge middleware architecture. Rewritten to
    match reality, then implemented (see above).
- FastAdmin header/sign-in logo now served from FastAPI `app/static/` at
  `/static/images/logo/busca-oficio-logo-principal.svg`. `ADMIN_SITE_*` values
  are URL paths, not filesystem paths. `load_dotenv()` moved to `app/__init__.py`.
- Added Sentry (errors + tracing + logs) for FastAPI and Next.js. Projects:
    `buscaoficio-backend` and `buscaoficio-frontend` in org `aag-k0`.
- Centralized backend logger in `app/config.py`; replaced auth `print()` hooks
  and added logs in email + routes. Tokens are never logged. Logger messages
  use f-strings, not `%s`.
- Frontend follows the official `@sentry/nextjs` three-runtime setup (no custom
  logger wrapper, no Jest Sentry mock, no example page, no `tunnelRoute`).
- Investigated fastadmin `authenticate` hook: root cause was comparing a
  re-hashed value instead of verifying the plaintext against the stored Argon2
  hash.
- Created `docs/auth.md`: full auth documentation for new developers.
- Opened GitHub issue [#1](https://github.com/Alfareiza/buscaoficio/issues/1)
  for email verification (backend email + template + frontend `/verify` page).

## Active decisions
- JWT strategy: **refresh token rotation with DB-backed revocation +
  double-submit fingerprint cookie** (Option B), decided 2026-08-15 after a
  `grill-me` design session. Access token 15 min, refresh token 30 days.
  Logout revokes *all* sessions for the user, not just the current device —
  chosen deliberately over a narrower "revoke this session only" approach.
- Do not commit or push work-in-progress branches without explicit
  go-ahead — `feature/jwt-frontend-refresh` is fully implemented and tested
  but intentionally left uncommitted per this rule.
- Frontend architecture (server-mediated vs. SPA vs. hybrid): **not yet
  decided**, actively being discussed with the user (see Current focus).
  Provisional lean (not agreed): **hybrid** — keep auth server-mediated
  exactly as #10 built it (HttpOnly-only cookies, strongest security
  posture, no client JS ever touches a token), and give the client a
  short-lived access token only for the specific future features that need
  it (live status, messaging/notifications — a two-sided marketplace will
  plausibly want these, and a Server Action has no way to receive a
  server-push update). Reasoning: no stated need today for a mobile app or
  third-party API consumer that would justify a full SPA rewrite, and the
  #10 work already built is exactly the auth foundation a hybrid model
  needs (nothing built so far would need to be redone under this option).
- Stay on template patterns (Makefile + watchers for OpenAPI sync).
- Keep Vercel as intended deploy target (serverless, not containers).
- MailHog remains for local email; Mailpit is a known alternative if we replace later.
- Prefer Docker for Postgres even when running API/FE on host.
- Auth routes are kept explicit (not using fastapi-users built-in router) to allow clear docstrings in OpenAPI docs.
- Sentry is DSN-optional: empty DSN disables the SDK. Pytest skips init
  (`"pytest" in sys.modules`).
- Frontend uses Sentry APIs directly (`Sentry.logger`, `Sentry.captureException`).
  Do not add a wrapper in `lib/utils.ts`.
- Keep the official Sentry/Next.js files as separate files. They look similar
  because the `init` options are the same today; they cannot be merged (three
  isolated JS runtimes / bundles). See `systemPatterns.md`.
- Do not add Session Replay, profiling, a `/sentry-example-page`, or
  `tunnelRoute` unless we explicitly decide to.

## Next steps (suggested)
1. **Resolve the frontend architecture question** (server-mediated vs. SPA
   vs. hybrid — see Current focus / Active decisions) before deciding what
   to do with `feature/jwt-frontend-refresh`. If server-mediated or hybrid
   is chosen, the branch as-built needs no rework. If full SPA is chosen,
   #10 needs a redesign (cookies would need to become JS-readable or a
   token-issuance endpoint would need adding) and issue #10 would need
   rewriting a third time.
2. Once resolved: get explicit go-ahead, then commit/push
   `feature/jwt-frontend-refresh`, open the PR for #10, wait for CI/rebase
   the same way #9/PR #11 was handled.
3. Close out issue #8 (parent) once #10's actual scope is settled and merged.
4. Implement email verification flow (GitHub issue #1).
5. Add `createsuperuser` management command under `commands/`.
6. If deploying: set Sentry env vars on Vercel (`SENTRY_ENVIRONMENT=production`)
   and add `SENTRY_AUTH_TOKEN` for frontend source maps.
7. Decide whether to evolve toward domain "busca oficio" features.

## Open considerations
- `refresh_tokens` rows are never purged — no cleanup job yet for
  expired/revoked rows (fine at current scale, worth a follow-up ticket
  later).
- Whether to migrate MailHog → Mailpit.
- Whether `$PORT` / container deploy will ever be needed (not required for Vercel path).
- Product domain requirements not yet defined beyond the template MVP.
- No RBAC or fine-grained permissions — only binary `is_superuser` flag exists today.
- First real Sentry error from a running app has not been verified end-to-end
  via MCP yet.
- Webpack Server Actions are not auto-instrumented; we capture caught errors
  manually. `withServerActionInstrumentation()` is available if we want traces
  on those actions later.
