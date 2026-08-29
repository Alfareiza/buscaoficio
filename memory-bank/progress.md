# Progress

## What works (template baseline)
- FastAPI auth: **passwordless email OTP** login/registration is the only
  linked flow (`/otp/request`, `/otp/verify`, `/register/{cliente,
  profesional}/otp`) — password-based `/jwt/login`/`/register*` were
  removed 2026-08-18 and **merged to `main` via PR #14**, see Session log
  below and `systemPatterns.md` § Passwordless OTP auth pattern.
  `/jwt/refresh`, `/jwt/logout`, and the users router are unaffected by
  which flow created the session.
- JWT refresh token rotation with DB-backed revocation + double-submit
  fingerprint cookie — **merged to `main`** (`0a8376b`, issue #9)
- User delete is a **soft-delete** (`usuarios.deleted_at` + `is_active=False`,
  refresh tokens revoked). FastAdmin and `DELETE /users/{id}` both go through
  `UserManager.delete`. Email/`google_sub` stay unique (no reuse). Apply
  migration `c8f3a91d4e20` on any database that already has the initial schema
  (including prod RDS).
- Frontend cookie forwarding + middleware-based silent refresh + reactive
  401 fallback — **merged to `main`** (`4d75bde`, issue #10). `proxy.ts`
  must not 307 Server Action POSTs (`next-action`); that made Logout a
  no-op in prod (2026-08-29). Actions `redirect()` themselves.
- `AuthCard` component (`components/auth/AuthCard.tsx`) drives the OTP
  flow on both `/login` and `/register`, which now share a route-group
  layout (`app/(auth)/layout.tsx`) so toggling between them feels instant
  (soft RSC nav, not a page reload) — **merged to `main` via PR #14**,
  2026-08-18. A follow-up UX polish batch (multi-box code input, cooldown
  bug fix, inline PNG email logo, required WhatsApp) is on branch
  `otp-ux-polish-required-whatsapp` (issue #15, pushed 2026-08-20, not yet
  PR'd) — see Session log below.
- Items CRUD + pagination
- Next.js auth pages + dashboard
- OpenAPI → typed FE client generation
- Docker Compose stack (backend, frontend, db, db_test, mailhog)
- Alembic migrations (user + item revisions present)
- CI workflows (FastAPI + Next.js), pre-commit, MkDocs
- Production deploy workflow (`.github/workflows/deploy.yml`): OIDC →
  ECR image push → SSH deploy to EC2 **works end-to-end** (2026-08-26);
  production runs login, Google Sign-In, RDS Postgres, FastAdmin. ECR
  pushes are idempotent ("already exists" = success) so re-runs can't fail
  on immutable SHA tags. Branch `18-deployment-workflow` is not yet merged
  to `main`. Vercel template leftovers remain but are not the prod path.
- Production **migrate** workflow (`.github/workflows/migrate.yml`):
  rewritten 2026-08-28 off Vercel. Path-filtered; SSH into EC2 and
  `alembic upgrade head` in the running backend container (RDS via
  container `DATABASE_URL`). Kept separate from deploy.

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
  see `activeContext.md`) — #9/#10 are already merged regardless, but this
  still shapes future features (live status, messaging)
- [ ] Open a PR for branch `otp-ux-polish-required-whatsapp` (issue #15,
  pushed 2026-08-20) once ready for review
- [ ] Close issue #8 (parent) once the architecture question above is settled
- [ ] Re-evaluate issue #1 (email verification) — OTP accounts are already
  `is_verified=true` at creation and the password registration path that
  could produce an unverified account is gone; decide whether to close #1,
  rescope it, or remove `/request-verify-token`/`/verify` too (not done yet)
- [ ] Decide the fate of `/forgot-password`/`/reset-password` (backend) and
  `/password-recovery` (frontend) — same vestigial status as #1 above, not
  acted on in the 2026-08-18 cleanup
- [ ] Cosmetic: many unrelated route docstrings (`items.py`, user/cliente/
  profesional CRUD) still say "Requires POST /auth/jwt/login" — harmless
  Swagger text, not a functional bug, left for a future sweep
- [ ] Cleanup job for expired/revoked `refresh_tokens` **and `email_otps`**
  rows (not started, not urgent at current scale)
- [ ] Confirm DBs restarted and migrations applied after port change
- [ ] Domain product features for "busca oficio" (not started)
- [ ] Production email provider (beyond MailHog)
- [x] Finish Deploy to EC2 job (SCP/SSH); box should run the SHA that ECR has
- [x] Rewrite `migrate.yml` for EC2/RDS (SSH + in-container Alembic), keep
  it separate from deploy
- [ ] Run prod Alembic (incl. `c8f3a91d4e20`) after the image with those
  revisions is on the box
- [ ] Create the first superuser to log into FastAdmin
  (https://api.buscaoficio.co/admin) — the 3-step bootstrap the user
  provided
- [ ] Prod secrets on the box, including Sentry DSN +
  `SENTRY_ENVIRONMENT=production` (frontend `SENTRY_AUTH_TOKEN` is already
  a GitHub Actions secret used at image-build time)
- [ ] Confirm a real error from the running app lands in Sentry (not done yet)
- [ ] Optional: replace MailHog with Mailpit
- [ ] `createsuperuser` management command (workaround now: sign up via the
  app's OTP flow, or FastAdmin, then promote via SQL)

## Known issues / gotchas
- `proxy.ts` must **never 307 a Server Action** (`next-action` header).
  Next posts actions to the current page (`POST /dashboard`); a
  middleware 307 is followed as another Flight POST to `/login` and is
  not a client navigation. Logout looked like a no-op in production
  (2026-08-29). Pass through; `logout-action.ts` / `items-action.ts`
  issue `redirect()` themselves.
- Changing `models.py` alone does **not** update OpenAPI client or DB schema.
- User delete is **soft**: `UserManager.delete` sets `deleted_at` and
  `is_active=False` rather than removing the row. FastAdmin lists hide
  tombstones. Unique email/`google_sub` still occupy the identity. Apply
  migration `c8f3a91d4e20` on prod or admin delete will 500 on a missing
  column (and the old FK error returns if you somehow hard-delete).
- Bare `pnpm run dev` / `uv run fastapi` skips watchers - use Makefile/`start.sh`.
- Production is EC2 + ECR, not Vercel. GitHub OIDC `sub` is
  `repo:Owner@id/repo@id:…` — a slug-form IAM trust policy fails AssumeRole.
- Prod schema changes: `migrate.yml` execs Alembic in the **current**
  backend container. If the same commit also deploys a new image, wait
  for deploy (or dispatch migrate after) so revision files exist in the
  container.
- Leftover Vercel serverless path has no `$PORT` wiring; ignore it for prod.
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
- `jest.mock("...")` needs a **relative** path, not `@/` — the SWC alias
  rewrite only applies to real `import` statements, not string arguments to
  `jest.mock()`. Every test file in this repo mocks via relative paths for
  this reason; a `@/`-aliased `jest.mock()` fails with a confusing "Cannot
  find module" pointing at the wrong line.
- After an HTTP call through the backend's `test_client`, `await
  db_session.refresh(some_object)` raises `InvalidRequestError: Instance
  ... is not persistent` — `conftest.py`'s `override_get_user_db` closes
  the session after each request. Re-query with `db_session.execute(select(...))`
  instead; that still works fine post-request.
- A backend HTTP route being unused by the current frontend does **not**
  make it "dead code" the way an unreferenced function is — it's still
  public API surface until you've confirmed no other client calls it.
  Worth an explicit question to the user rather than inferring from grep
  results alone before deleting a route (see the 2026-08-18 removal below).

## Session log (2026-08-29)
- Diagnosed prod Logout no-op: Server Action POST `/dashboard` 307'd by
  `proxy.ts`, Flight client replayed the same `next-action` onto
  `/login`, UI stayed on dashboard. Session cookies absent; only
  `lastGoogleIdentity` was sent.
- `proxy.ts` now passes `next-action` requests through instead of 307
  to `/login`. `logout()` always clears cookies and redirects.
- Documented in memory bank, `docs/auth.md`, `.cursorrules`,
  `nextjs-frontend/.CLAUDE.md`.

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
- **#9 and #10 have since been committed to `main`** (`0a8376b`, `4d75bde`)
  — confirmed via `git log` in the 2026-08-18 session below; this file's
  earlier "not yet committed" language was stale until this update.

## Session log (2026-08-18) — passwordless OTP migration + auth UX polish
- Somewhere before this conversation picked up (context was compacted/reset
  mid-session, so exact turn-by-turn history isn't available), password
  auth was fully replaced with passwordless email OTP as the frontend's
  only login/registration flow: backend `OtpManager`
  (`app/otp_manager.py`), `email_otps` table (migration `a067ad066d81`),
  routes `/otp/request`, `/otp/verify`, `/register/{cliente,profesional}/otp`;
  frontend `otp-auth-action.ts` + `AuthCard.tsx`. `docs/auth.md` gained the
  full design writeup (§ "0 · Passwordless login"). See `systemPatterns.md`
  § Passwordless OTP auth pattern and `activeContext.md` for what's known.
- Picked up mid-session (disk-full error interrupted the prior attempt;
  resumed after the user freed space) fixing test fallout from that
  migration: `registerPage.test.tsx`/`loginPage.test.tsx` were still
  testing the old password forms that no longer render; rewrote them for
  the redirect/AuthCard reality. Added `AuthCard.test.tsx` (had no coverage
  before). Fixed `register.test.ts` for a new required `nombre_completo`
  field. Fixed a real `SubmitButton` type bug (`className` typed required
  despite a default value) found via `tsc` in the process.
- **Auth pages UX polish**, per user request referencing a Dribbble sign-in
  page as inspiration: split `BuscaOficioLogo` into `BuscaOficioMark`/
  `BuscaOficioWordmark`; added `AuthCard`'s `intent` prop (login/register
  copy + toggle link); moved `/login`+`/register` into a shared
  `app/(auth)/layout.tsx` route group so toggling between them is a soft
  RSC nav instead of a reload (verified via network trace); `/register`
  went from a bare redirect back to a real page. Verified the whole flow
  live via `playwright-cli` (Chrome extension wasn't connected) — email →
  OTP → dashboard, plus the login↔register toggle. Had to restart the dev
  server (port 3000) after deleting `.next/` mid-run.
- **Removed the now-fully-dead password-based auth**, at the user's
  request to clean up "unused code in regard to this feature." Investigated
  via the codebase graph (`codebase-memory-mcp`) plus grep cross-checks
  (the graph had a few stale orphaned nodes, e.g. a deleted folder that
  still showed up — don't trust it blindly for deletion decisions). Found
  a real fork: frontend `login-action.ts`/`register-action.ts` had zero
  production callers (safe, unambiguous delete), but the backend
  `/jwt/login`/`/register*` routes were still live, working endpoints
  explicitly documented as "kept for backward compatibility" — a route
  being unused by the current frontend isn't the same as dead code; it's
  still public API surface. Asked the user directly whether anything else
  calls those routes rather than assuming from the code — confirmed "only
  this frontend nextjs project" — then removed both frontend and backend.
  Full list of what was deleted/changed: see `activeContext.md` § Recent
  changes. Also had to fix two backend tests that used `/jwt/login` as
  scaffolding rather than testing it directly (`test_auth_refresh.py`'s
  login helper, `test_users.py::test_updates_password`) — not a coverage
  loss, since `/otp/verify` calls the exact same `build_session_response()`.
  Regenerated `openapi.json` + the frontend OpenAPI client so the generated
  `authJwtLogin`/`registerRegister` bindings are gone too. Backend 103/104
  (1 pre-existing, unrelated email-subject-text failure from earlier
  uncommitted work in this branch), frontend 45/45, `tsc`/`eslint`/`ruff`
  clean.
- All of the above was committed and merged to `main` via **PR #14**
  (rebase-merged 2026-08-18) once given explicit go-ahead, after fixing
  three CI failures — see the 2026-08-20 session log below for the
  follow-up UX polish batch.

## Session log (2026-08-25) — EC2 deploy workflow + OIDC trust policy
- Walked through `.github/workflows/deploy.yml` OIDC step
  (`aws-actions/configure-aws-credentials@v4` + `AWS_DEPLOY_ROLE_ARN`).
- `sts:AssumeRoleWithWebIdentity` failed until the IAM trust policy's
  `sub` was changed from `repo:Alfareiza/buscaoficio:ref:refs/heads/…` to
  GitHub's numeric-ID form
  `repo:Alfareiza@63620799/buscaoficio@1329243606:*`.
- After that, Build & push (backend + frontend) succeeded; Deploy to EC2
  still failing. Images in ECR are tagged with the commit SHA; the box
  has not pulled them yet.

## Session log (2026-08-26) — Deploy pipeline stabilization + ECR immutable-tag fix
- Production is up end-to-end (login, Google Sign-In, RDS Postgres,
  FastAdmin) on branch `18-deployment-workflow`; the only remaining action
  is creating the first superuser for FastAdmin (3-step bootstrap).
- Fixed the recurring `"image tag … already exists … tag is immutable"`
  ECR failure: `deploy.yml`'s build jobs now treat that push rejection as
  success (same SHA = same content, immutability guarantees it), so GitHub
  re-runs, `workflow_dispatch`, and duplicate pushes all deploy cleanly.
  The `docker image prune` on the box (disk-full fix from `9372d34`) is
  unrelated to this ECR error — no manual prune ever unblocks it.
- Recent pipeline commits: `0713267` (opaque prod 500s, squashed
  migrations), `73ae711` (concurrency per ref), `9372d34` (prune after
  `up -d` so old images are actually orphaned), `20dc245` (Google redirect
  to 0.0.0.0:3000), `ee94b4f` (pnpm via Corepack).

## Session log (2026-08-20) — OTP UX polish: multi-box input, cooldown fix, required WhatsApp
- Picked up a second, larger batch of uncommitted OTP UX work sitting
  directly on `main` from an earlier interrupted session: a multi-box
  `OtpCodeInput` component, a real resend-cooldown countdown + "Verificando…"
  state in `AuthCard.tsx`, a CID-inlined PNG logo replacing inline SVG/CSS
  vars in the OTP email template, and a real `OtpManager` bug fix (the
  resend-cooldown check compared elapsed time against `OTP_LIFETIME -
  RESEND_COOLDOWN_SECONDS` instead of `RESEND_COOLDOWN_SECONDS` directly,
  silently blocking resend for ~570s instead of the intended 30s — fixed
  and the cooldown constant raised to a straight 60s). Verified all of it
  (backend 20/20 targeted tests, `ruff`, frontend `tsc`/`eslint`) and, along
  the way, found and fixed a 335s real-timer bug in `AuthCard.test.tsx`
  (the resend countdown's real `setTimeout` chain ran in wall-clock time
  under test; fixed with `jest.useFakeTimers()`) and removed an accidental
  duplicate `busca-oficio-logo-principal copy.svg` file.
- User asked to make the **WhatsApp field required** (not optional) in the
  onboarding-name step. Updated `AuthCard.tsx`: label, `handleContinueName`
  validation, and the Continuar button's disabled state all now treat
  WhatsApp like the required name field. Updated `AuthCard.test.tsx`
  accordingly (empty/invalid WhatsApp blocks Continuar; valid WhatsApp is
  sent as E.164 on submit).
- While fixing the WhatsApp tests, found `AuthCard.tsx::handleVerifyOtp`
  had a hard-coded `setStep("onboarding-name"); return;` at the top —
  added during the user's own manual testing — that made the real
  `verifyOtpAction` call, the `new_user`/`existing_user` branch, and
  `setRegistrationToken` all unreachable dead code. This broke real OTP
  login/verification and 6 tests. Flagged it to the user via
  `AskUserQuestion` rather than assuming it was safe to touch (it was their
  own recent edit); they confirmed reverting it. All 17 `AuthCard.test.tsx`
  tests green afterward.
- No open GitHub issue covered this batch — opened
  [#15](https://github.com/Alfareiza/buscaoficio/issues/15). Branched
  `otp-ux-polish-required-whatsapp` from an up-to-date `main`, staged
  everything feature-related (left out `.claude/settings.json`, a personal
  Claude Code hook config unrelated to the feature), ran
  `pre-commit run --all-files` (one `generate-frontend-client` failure was
  a transient race with the locally-running `watcher.js`/`next dev`
  processes — passed cleanly on retry), committed, and pushed. **Not yet
  opened as a PR.**

## Session log (2026-08-28) — user soft-delete + prod migrate workflow
- Production FastAdmin could not delete a user: `refresh_tokens_user_id_fkey`.
  Implemented `usuarios.deleted_at` (migration `c8f3a91d4e20`). Delete
  stamps `deleted_at`, sets `is_active=False`, revokes refresh tokens.
  Email/`google_sub` uniqueness unchanged (no reuse). FastAdmin hides
  tombstones. 147/147 backend tests green. Migration not applied (review
  first, then `make docker-migrate-db` / prod `migrate.yml`).
- Rewrote `.github/workflows/migrate.yml` from Vercel CLI + `vercel env
  pull` + runner Alembic to the same SSH pattern as `deploy.yml`:
  `compose exec -T backend alembic upgrade head`. Triggers only on
  Alembic paths (plus the workflow file). Deploy stays independent.
