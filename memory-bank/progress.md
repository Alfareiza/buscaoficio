# Progress

## What works (template baseline)
- FastAPI auth (JWT register/login/verify/reset) + users router
- JWT refresh token rotation with DB-backed revocation + double-submit
  fingerprint cookie — **merged to `main` via PR #11** (issue #9)
- Frontend cookie forwarding + middleware-based silent refresh + reactive
  401 fallback (branch `feature/jwt-frontend-refresh`, **fully implemented
  and tested, not yet committed** — see Session log below and issue #10)
- Items CRUD + pagination
- Next.js auth pages + dashboard
- OpenAPI → typed FE client generation
- Docker Compose stack (backend, frontend, db, db_test, mailhog)
- Alembic migrations (user + item revisions present)
- CI workflows (FastAPI + Next.js), pre-commit, MkDocs
- Vercel deploy docs / workflow templates for FE and BE

## Local customizations done
- [x] Postgres host ports remapped to **5434** (db) and **5435** (db_test)
- [x] `.env` / `.env.example` updated for new ports
- [x] Compose `TEST_DATABASE_URL` pointed at `db_test:5432`
- [x] Backend API port remapped to **8001**
- [x] Explicit READMEs for root / backend / frontend
- [x] Memory bank created under `memory-bank/`
- [x] `docs/auth.md` created — full auth documentation for new developers
- [x] Module docstring added to `app/routes/auth.py` referencing `docs/auth.md`
- [x] `fastapi_backend/README.md` links to `docs/auth.md`
- [x] Sentry + centralized backend logger (`app.config.logger`); frontend uses
  official `@sentry/nextjs` APIs directly
- [x] Sentry projects `buscaoficio-backend` / `buscaoficio-frontend` in org `aag-k0`
- [x] FastAdmin site name + header/sign-in logo served from `/static`

## What's left / unknown
- [ ] **Decide frontend architecture** (server-mediated vs. SPA vs. hybrid —
  see `activeContext.md`) — blocks whether #10 ships as-is or needs rework
- [ ] Commit + push `feature/jwt-frontend-refresh` and open PR for #10
  (waiting on explicit go-ahead — do not commit/push without it — and on
  the architecture decision above)
- [ ] Close issue #8 (parent) once #10 is merged
- [ ] Cleanup job for expired/revoked `refresh_tokens` rows (not started, not
  urgent at current scale)
- [ ] Confirm DBs restarted and migrations applied after port change
- [ ] Domain product features for "busca oficio" (not started)
- [ ] Production email provider (beyond MailHog)
- [ ] Prod secrets / Vercel projects wiring (if deploying), including Sentry
  DSN + `SENTRY_ENVIRONMENT=production` + frontend `SENTRY_AUTH_TOKEN`
- [ ] Confirm a real error from the running app lands in Sentry (not done yet)
- [ ] Optional: replace MailHog with Mailpit
- [ ] Email verification flow — backend email + template + frontend page (GitHub issue #1)
- [ ] `createsuperuser` management command

## Known issues / gotchas
- Changing `models.py` alone does **not** update OpenAPI client or DB schema.
- Bare `pnpm run dev` / `uv run fastapi` skips watchers - use Makefile/`start.sh`.
- Vercel is serverless, not Docker; no `$PORT` wiring in this repo for that path.
- Mixing local and Docker runs is discouraged by upstream docs.
- Default DB credentials (`postgres`/`password`) are local-only.
- `on_after_request_verify` logs `user.id` only — verification email not yet sent.
- No `createsuperuser` command; must promote via SQL (`UPDATE "user" SET is_superuser = true WHERE email = '...'`).
- fastadmin `authenticate` hook must use `PasswordHelper().verify_and_update(plain, stored)` — re-hashing produces a different hash every time (random salt).
- httpx `AsyncClient` test fixture must use `base_url="https://..."` (not
  `http://`) — Secure-flagged cookies are silently dropped by the client's
  cookie jar over plain HTTP, causing confusing 401s on anything that reads
  cookies (e.g. the refresh endpoint) even though the cookies were set fine.
- `UserManager.get(user_id)` is the fastapi-users method to fetch a user by
  UUID — there is no `get_by_id`.
- Any DB write inside a custom auth route needs an explicit `await
  db.commit()`. The test harness's `get_async_session` override closes the
  session right after the request completes, silently rolling back anything
  that was only `flush()`-ed.
- Server-to-server `fetch()`/axios responses' `Set-Cookie` headers do **not**
  reach the browser automatically — only same-origin browser→backend calls
  get that for free. Any Server Action or middleware that calls FastAPI on
  the user's behalf must manually re-apply the backend's `Set-Cookie`
  headers onto its own response (`lib/auth-cookies.ts`'s
  `forwardAuthCookies`).
- jsdom (Jest's default test environment) lacks the `Request`/`Response` Web
  APIs `next/server`'s `NextRequest` needs — any test importing `NextRequest`
  (e.g. `proxy.test.ts`) needs `/** @jest-environment node */` at the top of
  the file.
- Next.js `redirect()` throws internally in production but a Jest mock of it
  does not — code that relies on `redirect()` halting execution must use an
  explicit `return redirect(...)`, or execution falls through past it under
  test (and can end up calling a downstream function with an undefined
  token).

## Session log (2026-08-10 / 2026-08-11)
- Indexed codebase; reviewed stack by section (FE/BE/DB/DevOps).
- Clarified E2E type safety, MailHog, Vercel vs containers.
- Walked OpenAPI watcher/`start.sh`/`openapi.json` flow.
- Clarified Alembic is required for model/DB changes beyond `make start-*`.
- Remapped DB ports for coexistence with another project.

## Session log (2026-08-12 / 2026-08-13)
- Debugged fastadmin `authenticate`: invalid salt → stored hash is Argon2, not bcrypt; fix is to verify not re-hash.
- Created `docs/auth.md` with full auth flow documentation.
- Added module docstring to `app/routes/auth.py` and link in `fastapi_backend/README.md`.
- Clarified email verification gap in docs; opened GitHub issue #1.

## Session log (2026-08-13)
- FastAdmin logo 404: `ADMIN_SITE_HEADER_LOGO` was a URL FastAPI did not serve
  (and earlier a filesystem/Next.js path). Copied SVG to `app/static/`, mounted
  `/static`, set header + sign-in logo URLs, load dotenv in `app/__init__.py`.
- Implemented Sentry (errors + tracing + logs) on FastAPI and Next.js.
- Created Sentry projects and wrote real DSNs to local `.env` / `.env.local`
  (not committed).
- Centralized backend logger in `app/config.py`; all app logs use f-strings.
- Frontend: official three-runtime files only. Removed custom `lib/utils.ts`
  logger, Jest Sentry mock, and optional `tunnelRoute`.
- Documented why server/edge/client init files look similar but must stay
  separate (isolated Next.js runtimes; `proxy.ts` is Edge).

## Session log (2026-08-15 / 2026-08-16)
- Reviewed the Hasura "JWT with GraphQL best practices" article against the
  existing implementation; identified gaps (no refresh tokens, no
  server-side logout invalidation, no OWASP fingerprinting, no silent
  refresh, no cross-tab logout sync).
- Opened GitHub issues [#8](https://github.com/Alfareiza/buscaoficio/issues/8)
  (parent/architecture), [#9](https://github.com/Alfareiza/buscaoficio/issues/9)
  (backend), [#10](https://github.com/Alfareiza/buscaoficio/issues/10)
  (frontend) to track the work without assumptions baked in.
- Ran a `grill-me` design session; decided **Option B** — refresh token
  rotation with DB-backed hash storage + rotation-on-reuse theft detection +
  a double-submit fingerprint cookie — over a simpler single-token approach.
  Logout revokes all sessions for the user, not just the current one.
- Implemented the full backend on branch `feature/jwt-refresh-tokens`:
  `RefreshToken` model + migration, `RefreshTokenManager` service,
  rewritten `/auth/jwt/login` + `/auth/jwt/logout`, new `/auth/jwt/refresh`,
  27 new tests, `docs/auth.md` rewritten. **Left uncommitted** per explicit
  instruction not to commit/push until told to.
- Found (via a user question about how the frontend would know an access
  token is about to expire) that the `expires_in` field in the login/refresh
  response returns the wrong lifetime (refresh token's, not access token's).
  Logged as a tracked bug in #9 rather than silently fixed, since it directly
  shapes how #10 should be implemented (decode the JWT `exp` claim
  client-side; don't trust `expires_in` as-is).
- Rewrote issues #9 and #10 to match what was actually built (Option A
  language removed; Requirement 3 in #10 corrected — it's a server-issued
  double-submit cookie, not a computed browser fingerprint, so there's no
  fingerprint-collection code needed on the frontend after all).
- Added two FAQ entries to `docs/auth.md`: how the frontend will know when
  to refresh, and what happens if a user just closes the tab instead of
  logging out.
- Found and fixed a broken half-refactor in `app/routes/auth.py` /
  `app/utils.py` (bad absolute import, one leftover call to a deleted
  private helper) that had crept in outside this conversation's edits —
  full backend suite (102/102) confirmed green after the fix.

## Session log (2026-08-17)
- Reviewed and approved backend refresh-token PR; user rebased and merged it
  — **#9 is now on `main`** (commit `0a8376b`).
- Discovered the app's actual architecture (Server Actions + Edge
  middleware, not a client SPA) breaks #10's original ticket assumptions
  (client-side JWT decoding, `BroadcastChannel`, direct browser→backend
  calls). User approved rewriting #10 to match reality.
- Implemented #10 on branch `feature/jwt-frontend-refresh`: cookie
  forwarding (`lib/auth-cookies.ts`), middleware-based silent refresh
  (`proxy.ts` rewrite), reactive 401 fallback (`lib/api-errors.ts` +
  `items-action.ts`), documented why cross-tab sync needs no code. Folded
  in the previously-tracked `expires_in` bug fix per user's choice. 104/104
  backend tests, all frontend suites green. **Left uncommitted** per
  standing instruction.
- User pushed back on the "Server Actions, not a client SPA" framing,
  explaining the product's intended client-server usage (cliente/profesional
  actions eventually calling the API directly, possibly SPA-oriented).
  Opened an architecture discussion (server-mediated vs. SPA vs. hybrid) —
  **not resolved**; user wants to keep talking it through. See
  `activeContext.md` for the full state and a provisional (unagreed) lean
  toward hybrid.
- Confirmed `docs/auth.md` already documents the full #10 implementation
  (cookie forwarding, silent refresh, reactive fallback, cross-tab
  reasoning, `expires_in` fix) — no additional doc changes needed this
  session, just this memory-bank sync.
