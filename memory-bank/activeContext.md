# Active Context

## Current focus
- **Sentry Logs empty for `logger.info` (logout, etc.), 2026-08-30.**
  Production errors reached Sentry; **zero** backend logs in 90 days.
  sentry-sdk 2.68 made `enable_logs` a no-op and turned off stdlib
  auto-collection unless `LoggingIntegration(capture_sentry_logs=True)`.
  Separately, `buscaoficio` inherited root WARNING so `logger.info` never
  called `callHandlers` (the 2.68 bridge — not a root handler uvicorn
  could strip). Fix: `capture_sentry_logs=True` + `configure_app_logger()`
  at INFO. See Recent changes.
- **Supabase pooler prepared statements (BUSCAOFICIO-BACKEND-W), 2026-08-29.**
  `statement_cache_size=0` alone did not fix Google re-login after
  logout. SQLAlchemy still calls `connection.prepare(name=None)`;
  asyncpg 0.29 treats that as a named statement (`__asyncpg_stmt_a__`)
  which collides on the transaction pooler. Real fix: also
  `prepared_statement_cache_size=0` + `prepared_statement_name_func=str`
  in `app/database.py`. See Recent
  changes.
- **Prod logout no-op (Server Action 307), 2026-08-29.** Clicking
  Logout on `app.buscaoficio.co/dashboard` posted the `logout` Server
  Action to `/dashboard`; `proxy.ts` 307'd to `/login` before the action
  ran (no `accessToken` on the request). The Flight client followed that
  307 as another POST of the same `next-action` to `/login` while the
  router tree still said `dashboard` — not a navigation. Fix: never 307
  a `next-action` request; `logout()` always clears cookies and
  `redirect("/login")` even if the backend revoke fails. See Recent
  changes.
- **Prod Alembic workflow rewritten for EC2/RDS, 2026-08-28.**
  `.github/workflows/migrate.yml` no longer pulls Vercel env. It SSHes
  to the box (same `EC2_HOST` / `EC2_SSH_KEY` as deploy) and runs
  `alembic upgrade head` inside the running `backend` container. Still
  **separate from** `deploy.yml`. Path filter:
  `fastapi_backend/alembic_migrations/**`, `alembic.ini`, and the
  workflow file. See Recent changes.
- **User soft-delete (`deleted_at`), 2026-08-28.** FastAdmin `/admin` (and
  `DELETE /api/v1/users/{id}`) could not remove a logged-in user:
  `refresh_tokens_user_id_fkey` blocked a hard `DELETE` on `usuarios`.
  Delete now stamps `usuarios.deleted_at`, sets `is_active=False`, and
  revokes refresh tokens. The row stays so unique email/`google_sub` still
  block reuse. Tombstones are hidden from FastAdmin lists/detail. Needs
  Alembic `c8f3a91d4e20` applied on the current prod DB (Supabase) before
  admin delete works
  there. See Recent changes.
- **Production deploy on EC2 (working, branch `18-deployment-workflow`,
  not yet merged to `main`).** `.github/workflows/deploy.yml` builds FE/BE
  images in Actions, pushes to ECR tagged with the commit SHA (push is
  idempotent — "tag already exists" is treated as success), then SSHes to
  the box to `docker compose pull && up -d`. Production is live: login,
  Google Sign-In, Supabase Postgres (temporary; RDS after launch), FastAdmin
  (https://api.buscaoficio.co/admin) all work. **Remaining action: create
  the first superuser** to log into FastAdmin, following the 3-step
  bootstrap the user provided. See Recent changes.
- **Google Sign-In, 2026-08-22/23, merged to `main` via PR #17** (branch
  `feature/google-sign-in`). Server-side OAuth 2.0 authorization code flow;
  reaches the same fork OTP verification already does (existing account
  logs in, new email still goes through mandatory role selection + WhatsApp
  before an account is created). See "Recent changes" below for full detail
  including two bugs found and fixed during the build (a login loop from
  `SameSite=Strict` cookies, and an intermittent clock-skew login failure)
  and two more fixed from code review after the PR was open (session-token
  replay, a concurrent-account-linking race).
- JWT session hardening: both backend refresh token rotation
  ([#9](https://github.com/Alfareiza/buscaoficio/issues/9), commit
  `0a8376b`) and frontend cookie forwarding/silent refresh
  ([#10](https://github.com/Alfareiza/buscaoficio/issues/10), commit
  `4d75bde`) are **merged to `main`**. `feature/jwt-frontend-refresh` is no
  longer an open branch — this superseded the "intentionally left
  uncommitted" note from earlier sessions.
- **Passwordless email OTP is now the only linked login/registration flow**
  (since 2026-08-18) — password-based `/jwt/login`, `/register`,
  `/register/cliente`, `/register/profesional` were built, used briefly,
  then **removed entirely** the same day once OTP was confirmed as the sole
  client-facing flow. **Merged to `main` via PR #14** (rebase-merged
  2026-08-18, commits `950f51d`/`ad1cdce`/`f4b4b2e`) after fixing three CI
  failures (missing `REGISTRATION_TOKEN_SECRET_KEY` env var, a ruff version
  mismatch, and the `generate-frontend-client` pre-commit hook inheriting
  the wrong `OPENAPI_OUTPUT_FILE`). See "Recent changes" below for both the
  OTP build and the removal.
- **OTP UX polish batch, 2026-08-20** (issue
  [#15](https://github.com/Alfareiza/buscaoficio/issues/15), branch
  `otp-ux-polish-required-whatsapp`, pushed, **not yet PR'd**): multi-box
  `OtpCodeInput`, a real `OtpManager` resend-cooldown bug fix, inline PNG
  logo in OTP emails, and a required WhatsApp field in onboarding. See
  Recent changes below.
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
- FastAdmin branding (site name + logo) is wired; issue #1 (email
  verification) is open but its premise likely changed now that OTP
  accounts are auto-verified and password registration is gone — see Next
  steps.

## Recent changes
- **Sentry stdlib logs (sentry-sdk 2.68), 2026-08-30.** Logout
  `logger.info` never appeared in Sentry Logs. Two gates: (1)
  `enable_logs=True` no longer bridges stdlib — need
  `capture_sentry_logs=True`; (2) logger effective level was WARNING.
  SDK patches `Logger.callHandlers`; fastapi-cli uvicorn `dictConfig`
  only names `uvicorn.*`.
- **SQLAlchemy + asyncpg named prepares on PgBouncer, 2026-08-29.**
  First pass (`statement_cache_size=0`) was insufficient:
  [BUSCAOFICIO-BACKEND-W](https://aag-k0.sentry.io/issues/BUSCAOFICIO-BACKEND-W)
  still 500'd `GET /auth/google/callback` after logout→Google, on
  `SELECT … FROM usuarios WHERE google_sub = $1`, name
  `__asyncpg_stmt_a__`. SQLAlchemy 2.0.36 always `prepare()`s; a `None`
  name becomes a named statement in asyncpg 0.29 regardless of
  asyncpg's cache size. `app/database.py` now sets both caches to 0
  and `prepared_statement_name_func=str` (`str()` → unnamed prepare).
  Alembic imports `ASYNC_CONNECT_ARGS` from `app.database` after
  `load_dotenv()`.
- **asyncpg `statement_cache_size=0` for PgBouncer, 2026-08-29.**
  Sentry [BUSCAOFICIO-BACKEND-T](https://aag-k0.sentry.io/issues/BUSCAOFICIO-BACKEND-T)
  on `GET /api/v1/auth/google/callback` during dialect init. First
  incomplete fix; superseded by the named-prepare change above.
- **Logout Server Action vs `proxy.ts` 307, 2026-08-29.** Production
  Logout did nothing. Network: `POST /dashboard` (`next-action`,
  `accept: text/x-component`, body `["$T"]`) → 307 → identical Flight
  POST to `/login`. Cookie header was only `lastGoogleIdentity` (also
  HttpOnly — session cookies were truly absent, not stripped by
  DevTools). `proxy.ts` matcher includes Server Action POSTs; no
  `accessToken` → `NextResponse.redirect("/login")` (307). The client
  does not treat a middleware 307 as `redirect()` from inside an
  action, so the tab stayed on the already-rendered dashboard (layout
  has no auth check). Location was `https://app.buscaoficio.co/login`
  — not the `0.0.0.0:3000` bind-address bug from Google complete.
  Changes: `denyDashboardAccess()` in `proxy.ts` returns
  `NextResponse.next()` when `next-action` is present;
  `logout-action.ts` always clears cookies and redirects (backend
  revoke is best-effort — a `{ message }` return was never shown).
  Tests in `proxy.test.ts` / `logout.test.tsx`. Documented in
  `docs/auth.md`, `systemPatterns.md`, `.cursorrules`,
  `nextjs-frontend/.CLAUDE.md`.
- **`migrate.yml` retargeted from Vercel to EC2, 2026-08-28.** Dropped
  `VERCEL_*` secrets, Vercel CLI, `vercel env pull`, and runner-side
  `pip install` + `source .env.local`. The job now uses
  `appleboy/ssh-action` like deploy: `docker compose -f
  docker-compose.prod.yml exec -T backend alembic upgrade head`. Env
  (including `DATABASE_URL` for RDS) comes from the on-box `.env`
  already injected into the container. Intentionally **not** folded into
  `deploy.yml`. Concurrent with deploy when a commit also changes
  backend/frontend: migrate uses whatever backend image is currently
  running — new migration files are only on the box after that image is
  pulled. Prefer running migrate after deploy has finished, or
  `workflow_dispatch` once the new SHA is up.
- **User soft-delete (`deleted_at`), 2026-08-28.** Production FastAdmin
  delete failed with `ForeignKeyViolationError` on `refresh_tokens`.
  Grilled decisions: no email/Google reuse (unique indexes unchanged);
  hide tombstones from Usuarios/Cliente/Profesional admin lists; set both
  `deleted_at` and `is_active=False`; no undelete in this pass.
  `UserManager.delete` is the single write path (API + `UserAdmin.delete_model`).
  OTP/Google treat a deleted email as occupied (login fails like inactive,
  register returns already-exists) and do not attach `google_sub` to a
  tombstone. Migration `c8f3a91d4e20_add_usuarios_deleted_at`. Backend
  147/147 tests green. Not committed.
- **Deploy pipeline stabilized + ECR immutable-tag fix, 2026-08-26
  (branch `18-deployment-workflow`).** Production is now running
  end-to-end: login, Google Sign-In, Postgres (now temporarily
  Supabase; RDS after launch), FastAdmin. Pipeline
  commits this week: `0713267` (opaque prod 500s, migrations squashed to a
  clean initial schema), `73ae711` (serialize runs per ref for duplicate
  push triggers), `9372d34` (image prune ordering — the 8GB EC2 disk had
  filled up), `20dc245` (Google Sign-In redirecting to 0.0.0.0:3000 in
  prod), `ee94b4f` (pnpm pinned via Corepack). The recurring
  `"tag already exists … tag is immutable"` ECR failure on re-runs was
  fixed by making the SHA-tagged push idempotent: "already exists" is
  treated as success, since same SHA = same content. Pending: create the
  first superuser for FastAdmin (3-step bootstrap from the user).
- **EC2/ECR deploy pipeline, 2026-08-25 (branch `18-deployment-workflow`,
  not yet on `main`).** Workflow `.github/workflows/deploy.yml`: parallel
  `build-backend` / `build-frontend` (OIDC → ECR login → `docker build
  --provenance=false` + push as `…/buscaoficio-{backend,frontend}:${{ github.sha }}`),
  then `deploy` copies `docker-compose.prod.yml` + `Caddyfile` via SCP and
  SSHes in to rewrite image tags in `/opt/buscaoficio/.env` and restart
  Compose. OIDC `AssumeRoleWithWebIdentity` initially failed because the
  IAM trust policy used slug form `repo:Alfareiza/buscaoficio:ref:refs/heads/…`
  while GitHub now emits
  `repo:Alfareiza@63620799/buscaoficio@1329243606:…`. Trust policy updated
  to the numeric-ID `sub` with `:*` (any branch of this repo); branch
  gating stays in the workflow YAML. After that fix, both image-push jobs
  succeeded; **Deploy to EC2 still failing** as of this update.
- **Google Sign-In, 2026-08-22/23, merged to `main` via PR #17.** Server-side
  OAuth 2.0 authorization code flow (`GET /auth/google/authorize` → Google →
  `GET /auth/google/callback` → a Next.js **Route Handler**
  `app/api/auth/google/complete/route.ts`, not a page, so the session is
  established server-side and the browser lands directly on `/dashboard`
  with no intermediate screen). Backend: `app/google_oauth_manager.py`
  verifies Google's `id_token` against Google's JWKS directly (no People
  API round trip). New `usuarios.google_sub` column (nullable, unique),
  matched first, then falls back to matching by verified email for accounts
  originally created via OTP (auto-links, backfills `google_sub`). A new
  `lastGoogleIdentity` cookie (not localStorage — needs to be readable by
  `/login`'s Server Component during render) remembers the last
  Google-signed-in user's name/email/photo so `/login` can show "Continuar
  como {first name}" on a return visit, including after a deliberate
  logout — the cookie deliberately outlives logout, cleared nowhere.
  - **Two real bugs found and fixed while building this:**
    1. **Login loop**: session cookies (`accessToken`/`refreshToken`/
       `fingerprintToken`) were `SameSite=Strict`. Google's redirect chain
       starts cross-site (accounts.google.com), and browsers judge SameSite
       by the chain's *initiator*, so Strict silently withheld the cookies
       on the final navigation back into the app — `proxy.ts` saw no
       session and bounced to `/login`, which invited clicking "Continuar
       con Google" again. Fixed: `lib/auth-cookies.ts`'s
       `AUTH_COOKIE_SAME_SITE` is now `"lax"`. OTP login never hit this
       since that flow is entirely same-site.
    2. **Intermittent login failure**: `ImmatureSignatureError: The token
       is not yet valid (iat)` — PyJWT validates `id_token` `iat`/`exp`
       against the local wall clock with zero tolerance by default, and
       Docker Desktop for Mac's Linux VM clock can lag a few seconds behind
       real time right after the host sleeps/wakes. Diagnosed by
       deliberately letting the error raise unhandled once (at the user's
       explicit request) to get a real Sentry issue + full traceback,
       rather than the generic caught-and-redirected error. Fixed: 30s
       `leeway` on `jwt.decode()` (`GOOGLE_ID_TOKEN_LEEWAY_SECONDS`).
    3. Also fixed in passing: local MailHog was silently unreachable —
       `docker-compose.yml` only overrode `MAIL_SERVER`, leaving a
       developer's real SMTP port/TLS settings (from a `.env` with live
       Hostinger creds) active against the MailHog container. Now overrides
       the full MailHog-compatible var set.
  - **Two more fixed from automated code review after the PR was open**
    (both real, verified against the actual code, not false positives):
    1. `google_session_token` (the short-lived token handed from the
       backend callback to the Route Handler) briefly rides in a redirect
       URL — unlike every other session-establishing value in this app,
       which never leaves an HttpOnly cookie or POST body — so it's
       exposed to browser history, request logs, and Sentry's request
       tracing. It was verified for signature+expiry only, with no
       single-use enforcement, so a leaked copy could be replayed within
       its 2-minute lifetime to open extra sessions. Fixed: a `jti` claim
       + new `used_google_session_tokens` table (mirrors `EmailOtp`'s
       `consumed_at` pattern), claimed atomically via a unique-constraint
       insert in `GoogleOAuthManager.consume_session_token_jti`.
    2. Two concurrent `/google/callback` requests linking the same
       not-yet-linked email (e.g. a duplicated/retried navigation) could
       both pass the `google_sub is None` check and race to commit; the
       loser hit the unique constraint as an unhandled `IntegrityError` →
       500. Fixed: caught, rolled back, row reloaded — same pattern already
       used in the OTP registration routes.
  - Migration `938ad64baf39` (add `google_sub`) already reviewed and
    applied by the user. Migration `67f2b3cd225f` (add
    `used_google_session_tokens`) generated, **not yet applied** — needs
    the same review-then-apply step.
  - `client_secret.json` (the downloaded Google OAuth credentials file) sat
    briefly untracked in the repo root; `client_secret*.json` added to
    `.gitignore` as a safety net. User is removing the file themselves.
  - Not built, deliberately mapped only: post-login redirect destination
    (a `LOGIN_REDIRECT` default vs. a resource-gated modal that releases
    back to the originally-requested resource) — see Open considerations.
- **OTP auth UX polish batch, 2026-08-20 (issue #15, branch
  `otp-ux-polish-required-whatsapp`, pushed, not yet PR'd).** Built on top
  of the merged OTP migration below:
  - New `OtpCodeInput` component (`components/auth/OtpCodeInput.tsx`):
    6 individual `<input maxLength=1>` boxes replacing the old single text
    field — keyboard nav (arrows/backspace), paste-splitting across boxes,
    auto-focus-advance, auto-submit on the 6th digit, shake animation
    (`otp-shake` keyframe added to `tailwind.config.js`) on a failed verify,
    remounted via a `key` bump to reset cleanly between attempts.
  - `AuthCard.tsx`: added a real resend-cooldown countdown (60s, matching
    `OtpManager.RESEND_COOLDOWN_SECONDS`) and an `isVerifying` state that
    hides the resend control and shows "Verificando…" while a code is being
    checked.
  - **Fixed a real `OtpManager` bug**: the resend-cooldown check compared
    elapsed code age against `OTP_LIFETIME - RESEND_COOLDOWN_SECONDS`
    instead of `RESEND_COOLDOWN_SECONDS` directly — with the old 30s
    cooldown constant and a 600s `OTP_LIFETIME`, this silently blocked
    resend for ~570s instead of 30s. Fixed the check and raised the
    constant to a straight 60s cooldown (`fastapi_backend/app/otp_manager.py`).
    New regression tests in `tests/test_otp_manager.py` and
    `tests/routes/test_auth_otp.py::test_resend_within_cooldown_still_returns_202_but_does_not_email`.
  - Replaced the OTP email's inline SVG mark (CSS custom properties,
    unsupported by most email clients) with a CID-attached PNG
    (`app/static/images/logo/busca-oficio-mark.png`, 1024×1024 RGBA),
    inlined via `fastapi-mail`'s `multipart/related` + `Content-ID`
    attachment support (`email.py::_inline_logo_attachment`). Source SVG
    kept alongside as design provenance, not referenced by code.
  - **Made WhatsApp required** (was optional) in the onboarding-name step:
    label dropped "(opcional)", `handleContinueName` validates it exactly
    like the name field, and the Continuar button stays disabled until it's
    a valid Colombian mobile number (`isValidColombianMobile` /
    `lib/colombian-mobile.ts`, extracted from the earlier onboarding work).
  - **Reverted a debug bypass** found in `AuthCard.tsx::handleVerifyOtp`
    (`setStep("onboarding-name"); return;` at the top of the function,
    added during the user's own manual testing) that made real OTP
    verification unreachable dead code — no code was actually checked,
    existing-user login never redirected, and `registrationToken` was never
    captured. Restored the real verify-then-branch-on-`new_user`/
    `existing_user` flow. Caught via 6 failing `AuthCard.test.tsx` tests;
    confirmed with the user before reverting (their own recent edit) rather
    than assuming it was safe to undo silently.
  - `.CLAUDE.md` (root/backend/frontend) and `docs/auth.md` rewritten with
    current stack tables, directory maps, and testing-gotcha sections —
    largely written in an earlier part of this session, committed together
    with this batch.
  - Backend 20/20 targeted tests green; frontend `AuthCard.test.tsx` 17/17;
    `tsc`/`eslint`/`ruff`/`pre-commit run --all-files` all clean (one
    transient `generate-frontend-client` failure was a race with the
    locally-running `watcher.js`/`next dev` processes, not a real issue —
    passed on retry).
- **Removed password-based auth (backend + frontend), 2026-08-18.** The
  Next.js frontend was the only client of the password-based routes, and
  since the passwordless OTP flow (`docs/auth.md` § "Passwordless login")
  became the only linked flow, they were dead weight:
  - Backend: deleted `POST /jwt/login`, `/register`, `/register/cliente`,
    `/register/profesional` from `app/routes/auth.py`; deleted the
    now-unused `ClienteRegisterCreate`/`ProfesionalRegisterCreate` schemas.
    `/forgot-password`/`/reset-password`/`/request-verify-token`/`/verify`
    were kept (still exist, still unlinked in the frontend) but are now
    vestigial — see `docs/auth.md` for why.
  - Backend tests: deleted `tests/main/test_main.py` (100% about the
    removed routes). `tests/routes/test_auth_refresh.py`'s login helper now
    goes through OTP (`/otp/request` + `/otp/verify`) instead of
    `/jwt/login` — refresh/logout/rotation behavior is agnostic to how the
    session started, so this is a like-for-like swap, not a coverage loss.
    `tests/routes/test_users.py::test_updates_password` now verifies the
    new password hash directly (via `PasswordHelper`) instead of
    round-tripping through the now-gone login route.
  - Frontend: deleted `login-action.ts`, `register-action.ts` (both already
    marked "Dormant since 2026-08-18" and had zero production callers —
    only their own dedicated tests called them) and those tests; deleted
    the now-orphaned `loginSchema`/`registerSchema` (and a pre-existing
    unused `onboardingNameSchema` found in the same pass) from
    `lib/definitions.ts`. Regenerated `openapi.json` and the frontend
    OpenAPI client (`app/openapi-client/*`) so the generated `authJwtLogin`/
    `registerRegister` bindings are gone too.
  - `docs/auth.md` updated throughout to drop "kept for backward
    compatibility" language for the removed routes and fix now-dangling
    `/jwt/login` references in surviving routes' docstrings/FAQ.
  - **Not done / known follow-ups:** many *unrelated* route docstrings
    across the backend (`items.py`, user/cliente/profesional CRUD, etc.)
    still say "Requires POST /auth/jwt/login" as generic boilerplate for
    "you need to be authenticated" — cosmetic only (Swagger descriptions),
    left alone as out of scope for this cleanup. Also didn't touch
    `/password-recovery` frontend pages or the backend
    forgot/reset/verify routes themselves, even though they're now
    functionally vestigial too (no password-login route left to use a
    reset password with) — that's a separate, unconfirmed scope expansion
    the user didn't ask for.
- **Auth pages UX polish (login/register), 2026-08-18, merged in PR #14.**
  Built on top of the OTP migration below:
  - `components/ui/BuscaOficioLogo.tsx` split into standalone
    `BuscaOficioMark` (svg only) and `BuscaOficioWordmark` (text only,
    "Busca" in `text-azul` / "Oficio" in `text-naranja`) — `BuscaOficioLogo`
    kept as a composite of the two for the two `/password-recovery` pages
    that still use the combined form.
  - `AuthCard` gained an `intent?: "login" | "register"` prop controlling
    the subtitle copy and a bottom toggle link ("No tengo cuenta.
    Registrarme" ↔ "Ya tengo una cuenta. Iniciar Sesión"), plus a legal
    line ("Al continuar, aceptas nuestros Términos y Política de
    Privacidad.") below the Continuar button — Términos/Política are plain
    text, not links, since those pages don't exist yet.
  - `/login` and `/register` moved into a shared `app/(auth)/layout.tsx`
    route group. The outer shell (background, card frame, side image) now
    lives in the layout instead of each page, so navigating between the two
    via the toggle link is a soft RSC navigation (confirmed via network
    trace: `GET /register?_rsc=...`, not a full document load) that doesn't
    remount the frame — this is what makes the login↔register toggle feel
    instant instead of a page reload.
  - `/register/page.tsx` changed from a bare `redirect("/login")` to
    actually rendering `<AuthCard intent="register" />` — it's a real page
    again, just sharing the same component and layout as `/login`.
  - Finding while doing this: **`jest.mock()` string arguments must use
    relative paths, not the `@/` alias** — Next's SWC transform rewrites
    `@/`-aliased imports at parse time in real `import` statements, but not
    inside a `jest.mock("@/...")` call, so it fails to resolve. Every test
    file in this repo already mocks via relative paths (`"../components/..."`)
    for this reason; keep following that convention.
- **Passwordless email OTP migration (backend + frontend), 2026-08-18,
  merged in PR #14.** Replaced password-based login/registration as the
  frontend's only flow (see `docs/auth.md` § "Passwordless login" for the
  full design writeup). Backend: `OtpManager` (`app/otp_manager.py`,
  modeled on `RefreshTokenManager`) + `email_otps` table (migration
  `a067ad066d81`) for 6-digit codes (10-min expiry, 5 attempts, 60s resend
  cooldown, hashed not stored raw); new routes `POST /otp/request`,
  `/otp/verify`, `/register/cliente/otp`, `/register/profesional/otp`; a
  short-lived signed `registration_token` proves OTP ownership between
  verify and registration so an abandoned signup never leaves a ghost
  account; OTP-created accounts get a random never-disclosed password
  (fastapi-users requires `hashed_password` non-null) and `is_verified=true`
  immediately. Frontend: `otp-auth-action.ts` (Server Actions calling the
  new routes) and `AuthCard.tsx` (multi-step client component: email → code
  → name → role, used in both `mode="page"` on `/login`/`/register` and
  presumably `mode="modal"` elsewhere). `docs/auth.md` gained the full "0 ·
  Passwordless login" section. This is what made the password-based routes
  removable a few hours later — see the removal entry above.
- **JWT refresh token rotation frontend (#10, merged to `main`,
  commit `4d75bde`):**
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
- **Prod Postgres is temporarily Supabase** (transaction-mode pooler
  `:6543`), decided 2026-08-29. After the app launches, switch
  `DATABASE_URL` to RDS `buscaoficio-1`. No engine-code change planned
  — `ASYNC_CONNECT_ARGS` already works on both (caches off +
  `prepared_statement_name_func=str`). Keep the dict through the switch.
- JWT strategy: **refresh token rotation with DB-backed revocation +
  double-submit fingerprint cookie** (Option B), decided 2026-08-15 after a
  `grill-me` design session. Access token 15 min, refresh token 30 days.
  Logout revokes *all* sessions for the user, not just the current device —
  chosen deliberately over a narrower "revoke this session only" approach.
- Do not commit or push work-in-progress branches without explicit
  go-ahead. `feature/jwt-frontend-refresh` (#10) was committed to `main`
  (`4d75bde`); the OTP passwordless migration, auth pages UX polish, and
  password-based auth removal (all 2026-08-18) were committed and merged
  via PR #14 once given the go-ahead. The 2026-08-20 OTP UX polish batch
  (issue #15, branch `otp-ux-polish-required-whatsapp`) was committed and
  pushed once explicitly requested — not yet opened as a PR.
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
- **Login is passwordless email OTP, not password auth** — decided and
  built 2026-08-18. Login and signup share one screen; the backend doesn't
  know which the user "meant" until the OTP is verified (see `docs/auth.md`
  § 0). This was a full replacement, not an addition — password-based
  `/jwt/login`/`/register*` were removed the same day (see below), not kept
  as a parallel option.
- **Scope of the password-auth removal, confirmed with the user
  2026-08-18:** asked explicitly whether anything besides the Next.js
  frontend calls the password-based backend routes before deleting them —
  user confirmed "my only client is this frontend nextjs project." That's
  why it was safe to delete the *backend* routes (`/jwt/login`,
  `/register`, `/register/cliente`, `/register/profesional`), not just the
  dead frontend Server Actions that called them — a backend HTTP route
  isn't "unused code" in the same sense as a function with no callers,
  since it's part of the public API contract regardless of what the current
  frontend does; needed an explicit answer, not an inference from the code.
- Stay on template patterns (Makefile + watchers for OpenAPI sync).
- **Production deploy is EC2 + ECR + Compose**, not Vercel. Vercel
  serverless leftovers stay in the repo until someone deletes them.
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
1. Apply prod migrations (including `c8f3a91d4e20`) via `migrate.yml`
   against the current Supabase `DATABASE_URL` once the backend image
   that contains those revisions is running — or `workflow_dispatch`
   after deploy. After launch: cut `DATABASE_URL` over to RDS.
2. Open a PR for branch `otp-ux-polish-required-whatsapp` (issue #15,
   pushed 2026-08-20) once ready for review.
3. **Resolve the frontend architecture question** (server-mediated vs. SPA
   vs. hybrid — see Current focus / Active decisions). Now somewhat
   independent of #10 (already merged) but still relevant to how future
   features (live status, messaging) get built.
4. Close out issue #8 (parent) once the architecture question above is settled.
5. **Re-evaluate GitHub issue #1 (email verification)** — its premise may
   have changed: OTP-created accounts are already `is_verified=true` at
   creation (receiving the code already proves mailbox ownership), and the
   password-based registration flow that could produce an unverified
   account was just removed. `/request-verify-token`/`/verify` still exist
   in the code but nothing in the current flow produces an account they'd
   act on — worth deciding whether to close #1 as no-longer-applicable,
   scope it down, or actually remove those routes too (not done in this
   session — see the removal entry's "Not done" note).
6. Decide the fate of `/forgot-password`/`/reset-password` and the
   frontend `/password-recovery` pages — same vestigial status as #5 above
   (no password-login route left to use a reset password with), flagged
   but not acted on.
7. Add `createsuperuser` management command under `commands/` — the
   go-to instruction for this changed from "`POST /auth/register` then
   promote in SQL" to "sign up via the app's OTP flow, or FastAdmin, then
   promote in SQL" (see `docs/auth.md`), but the underlying gap is the same.
8. Production Sentry: `SENTRY_ENVIRONMENT=production` on the box, plus
   `SENTRY_AUTH_TOKEN` (already wired as a GitHub secret for the frontend
   image build / source maps).
9. Decide whether to evolve toward domain "busca oficio" features.
10. Optional cosmetic cleanup: many unrelated route docstrings (`items.py`,
   user/cliente/profesional CRUD) still say "Requires POST /auth/jwt/login"
   as generic authenticated-request boilerplate — harmless (Swagger text
   only) but worth a sweep to say `/otp/verify` instead, next time someone
   is in those files.

## Open considerations
- **Post-login redirect destination is hardcoded, not yet designed (2026-08-22, explicitly mapped but NOT implemented per the user's request — "let's keep it that way so far just mapped").**
  Today `AuthCard.tsx`'s `finish()` always does `router.push("/dashboard")` regardless of how/why the user reached the login screen — there is no concept yet of "where should this login actually land." Two real scenarios need to be told apart:
  1. **Direct visit to `/login`** (the user chose to log in, no prior context) → should land on a configurable default, referred to as `LOGIN_REDIRECT` — i.e. a single named app-level setting for "where a voluntary login lands," not a value inlined at the call site.
  2. **Gated-resource access** (the user hit a protected page/action while logged out, or a logged-in-but-unauthorized action) → login should happen **in a modal**, without leaving the page, and on success should **release access to the originally-requested resource** — resume/redirect back to what they were actually trying to do, not bounce to the generic default.
  Relevant existing pieces this would build on: `components/auth/AuthModal.tsx` already exists (`mode="modal"` on `AuthCard`) but per its own comment is "not wired to a trigger anywhere in the app yet" — scenario 2 is exactly its intended use case. `proxy.ts`'s redirect-to-`/login` on a dead/missing session (see [[project_auth_otp_migration]] and the Google Sign-In session-cookie work) currently does **not** preserve the originally-requested URL — that's the specific gap scenario 2 needs closed (e.g. a `?next=` param or similar). Not designed further than this — no return-URL param format, no decision on which protected actions should trigger the modal vs. a full redirect, chosen yet.
- `email_otps` rows are never purged either — same known gap as
  `refresh_tokens` below, now duplicated across two tables.
- `refresh_tokens` rows are never purged — no cleanup job yet for
  expired/revoked rows (fine at current scale, worth a follow-up ticket
  later).
- `/forgot-password`, `/reset-password`, `/request-verify-token`, `/verify`
  (backend) and `/password-recovery` (frontend) are now functionally
  vestigial — still work, still exist, but nothing in the current OTP-only
  flow can reach an account they'd meaningfully act on. Not removed in the
  2026-08-18 cleanup (unconfirmed scope), but worth a deliberate decision
  rather than leaving them as silent dead weight indefinitely.
- Whether to migrate MailHog → Mailpit.
- Whether to delete leftover Vercel serverless files (`api/index.py`,
  template deploy docs). `migrate.yml` is no longer Vercel.
- Race if the same push triggers both `deploy.yml` and `migrate.yml`:
  migrate may `exec` Alembic in the **old** backend container before
  `docker compose pull && up -d` finishes. No `workflow_run` / `needs`
  coupling by design (keep migrate separate). Operator: wait for deploy,
  then dispatch migrate.
- Product domain requirements not yet defined beyond the template MVP.
- No RBAC or fine-grained permissions — only binary `is_superuser` flag exists today.
- First real Sentry error from a running app has not been verified end-to-end
  via MCP yet.
- Webpack Server Actions are not auto-instrumented; we capture caught errors
  manually. `withServerActionInstrumentation()` is available if we want traces
  on those actions later.
