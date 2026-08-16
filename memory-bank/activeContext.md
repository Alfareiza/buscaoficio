# Active Context

## Current focus
- JWT session hardening: refresh token rotation is implemented on the backend
  (branch `feature/jwt-refresh-tokens`, **uncommitted**, tracked as GitHub
  issue [#9](https://github.com/Alfareiza/buscaoficio/issues/9)). Frontend
  side (silent refresh, cross-tab logout sync) is issue
  [#10](https://github.com/Alfareiza/buscaoficio/issues/10), not started.
- FastAdmin branding (site name + logo) is wired; auth gaps (email
  verification, #1) are still open behind the JWT work above.

## Recent changes
- **JWT refresh token rotation (backend, #9 — not yet committed):**
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
    `tests/routes/test_auth_refresh.py`); full backend suite 102/102 green.
  - **Known bug, tracked in #9, not yet fixed:** the `expires_in` field in
    the login/refresh JSON response returns the refresh token's lifetime
    (30 days) instead of the access token's (15 min). Frontend (#10) must
    not trust it — decode the JWT's own `exp` claim client-side instead.
  - `docs/auth.md` rewritten with a full "Refresh tokens & rotation"
    section plus FAQ entries on token-expiry detection and closing the
    browser without logging out.
  - Issues #8 (parent/architecture decision), #9, #10 all rewritten to
    reflect the actual implementation (Option B — refresh rotation — was
    chosen over Option A — single long-lived token — deliberately, to keep
    the access-token blast radius small without hurting UX).
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
  go-ahead — `feature/jwt-refresh-tokens` is fully implemented and tested
  but intentionally left uncommitted per this rule.
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
1. Get explicit go-ahead, then commit/push `feature/jwt-refresh-tokens` and
   open the PR for #9 (backend refresh token rotation).
2. Fix the `expires_in` bug in `app/routes/auth.py` before or alongside that
   PR (small change, tracked in #9).
3. Start frontend work for #10: silent refresh (decode JWT `exp`, do not
   trust `expires_in`), cross-tab logout sync, verify fingerprint cookie
   round-trips correctly (no fingerprint-collection code needed — it's a
   server-issued cookie, not a computed value).
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
