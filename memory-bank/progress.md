# Progress

## What works (template baseline)
- FastAPI auth (JWT register/login/verify/reset) + users router
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
