# Progress

## What works (template baseline)
- FastAPI auth (JWT register/login/verify/reset) + users router
- Items CRUD + pagination
- Next.js auth pages + dashboard
- OpenAPI → typed FE client generation (backend side is current; **frontend generated
  client is stale** — see issue #7 and `systemPatterns.md`)
- Docker Compose stack (backend, frontend, db, db_test, mailhog)
- Alembic migrations (user + item + Cliente/Profesional shared-PK revisions present)
- CI workflows (`ci.yml`, `pre-commit.yml`, `migrate.yml`, release), MkDocs — **all now
  green except `pre-commit`'s last hook, blocked on issue #7**
- Vercel deploy docs / workflow templates for FE and BE

## Domain work (past template baseline)
- [x] `Usuario`/`Cliente`/`Profesional` shared-PK model (2026-08-14, commit `3d11cac`)
- [x] Role-specific registration endpoints (`/api/v1/auth/register/{cliente,profesional}`)
- [x] All routers moved under `/api/v1` prefix
- [x] FastAdmin panel built out for Usuario/Cliente/Profesional
- [ ] Next.js registration flow updated to match (issue #7 — **not started**)
- [ ] Further busca-oficio product features (matching, listings, etc.)

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
- [ ] Fix Next.js registration flow for Cliente/Profesional (GitHub issue #7)
- [ ] Confirm DBs restarted and migrations applied after port change
- [ ] Further domain product features for "busca oficio" beyond Cliente/Profesional
- [ ] Production email provider (beyond MailHog)
- [ ] Prod secrets / Vercel projects wiring (if deploying), including Sentry
  DSN + `SENTRY_ENVIRONMENT=production` + frontend `SENTRY_AUTH_TOKEN`
- [ ] Confirm a real error from the running app lands in Sentry (not done yet)
- [ ] Optional: replace MailHog with Mailpit
- [ ] Email verification flow — backend email + template + frontend page (GitHub issue #1)
- [ ] `createsuperuser` management command
- [ ] Optional: register this repo on coveralls.io (Coveralls CI steps are
  `continue-on-error: true` in the meantime)
- [ ] Optional: decide whether the plain `POST /register` route should be removed now
  that role-specific registration exists

## Known issues / gotchas
- Changing `models.py` alone does **not** update OpenAPI client or DB schema.
- Bare `pnpm run dev` / `uv run fastapi` skips watchers - use Makefile/`start.sh`.
- Vercel is serverless, not Docker; no `$PORT` wiring in this repo for that path.
- Mixing local and Docker runs is discouraged by upstream docs.
- Default DB credentials (`postgres`/`password`) are local-only.
- `on_after_request_verify` logs `user.id` only — verification email not yet sent.
- No `createsuperuser` command; must promote via SQL (`UPDATE "user" SET is_superuser = true WHERE email = '...'`).
- fastadmin `authenticate` hook must use `PasswordHelper().verify_and_update(plain, stored)` — re-hashing produces a different hash every time (random salt).
- `pre-commit` hooks gated by a `files:` regex (e.g. `generate-openapi-schema`,
  `generate-frontend-client`) still run under `--all-files` if any tracked file
  anywhere in the repo matches the regex — they are not scoped to the current diff.
- The `ruff` pinned in `fastapi_backend/pyproject.toml` dev deps (`<0.2`) is far behind
  the `ruff-pre-commit` hook's pinned `v0.12.2` — `uv run ruff format` and the actual
  pre-commit hook disagree on formatting. Use `uvx ruff@0.12.2` to match CI exactly.
- Next.js registration (`register-action.ts`) is broken against the current backend
  schema (missing `nombre_completo`); masked today only because the committed
  generated client (`app/openapi-client/*`) is stale. See issue #7.

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

## Session log (2026-08-14)
- (Prior session, undocumented until now) Cliente/Profesional shared-PK refactor:
  `Usuario`/`Cliente`/`Profesional` model, role-specific registration endpoints,
  `/api/v1` prefix on all routers, FastAdmin panel buildout. Commit `3d11cac`.
- Added `.github/workflows/migrate.yml` for on-demand production Alembic migrations
  (path-filtered push to `main`, or manual `workflow_dispatch`). Issue #5, PR #6.
- Found `pre-commit`/`ci.yml`/Coveralls had never fully passed since the initial
  commit. Root cause chain: broken `docs/CHANGELOG.md` symlink (fixed by adding the
  missing root file) → missing repo secrets (fixed with CI-only hardcoded test values
  in `ci.yml`/`pre-commit.yml`) → ruff version drift between `pyproject.toml` (`<0.2`)
  and the pinned pre-commit hook (`v0.12.2`) (fixed by reformatting with `uvx
  ruff@0.12.2`, 12 files + 1 unused import) → Coveralls not registered for this repo
  (made non-blocking with `continue-on-error: true`). Verified with full pytest suite
  (75 passed) at each step.
- Regenerating the frontend OpenAPI client to unblock the last pre-commit hook
  surfaced that `nextjs-frontend`'s registration flow was never updated for the
  Cliente/Profesional refactor (missing `nombre_completo`, wrong endpoint). Reverted
  the client regen and opened issue #7 instead of patching product behavior blind.
- Updated the memory bank (this file, `activeContext.md`, `systemPatterns.md`,
  `techContext.md`, `projectbrief.md`, `productContext.md`) to catch up on both the
  undocumented Cliente/Profesional refactor and this session's CI work.
