# Active Context

## Current focus
- CI is green again after being broken since the initial commit (see
  `systemPatterns.md` → "CI/CD pattern"); `pre-commit` is intentionally still red on
  the `generate-frontend-client` hook, pending issue #7 below.
- Highest-priority known gap: the Next.js registration flow does not match the
  Cliente/Profesional backend (GitHub issue #7) — the form/action never collects
  `nombre_completo` and still targets the plain `/register` instead of
  `/register/cliente` / `/register/profesional`. Fixing this is real feature work
  (form UI + `registerSchema` + server action), not wired up yet.
- Otherwise: FastAdmin branding (site name + logo) is wired; next product work is
  auth gaps (email verification) unless we deploy and wire Vercel env vars.
- Auth system understanding, documentation, and gap identification.

## Recent changes (2026-08-14, this session)
- Added `.github/workflows/migrate.yml`: runs `alembic upgrade head` against
  production on push to `main` touching `fastapi_backend/alembic_migrations/**` or
  `alembic.ini`, or via manual `workflow_dispatch`. Mirrors the migration step already
  in `prod-backend-deploy.yml` for consistency. GitHub issue
  [#5](https://github.com/Alfareiza/buscaoficio/issues/5), PR
  [#6](https://github.com/Alfareiza/buscaoficio/pull/6).
- Discovered and fixed `pre-commit`/`ci.yml`/`Coveralls` had never fully passed on this
  repo (broken `docs/CHANGELOG.md` symlink blocked every run at the first hook; missing
  repo secrets; ruff version drift between `pyproject.toml` and the pinned pre-commit
  hook). Full root-cause chain and fixes documented in `systemPatterns.md`.
- Regenerating the frontend OpenAPI client (part of chasing the above) surfaced that
  it had silently drifted from the Cliente/Profesional refactor — opened GitHub issue
  [#7](https://github.com/Alfareiza/buscaoficio/issues/7) rather than patching the
  registration flow blind, since it's real product behavior, not CI plumbing.

## Recent changes (earlier, undocumented until now)
- **Cliente/Profesional refactor** (2026-08-14, commit `3d11cac`): first real domain
  work past the template baseline. Full details in `systemPatterns.md` →
  "Cliente/Profesional domain model" and `projectbrief.md`. Short version: `Usuario`
  (fastapi-users `User`) plus shared-PK `Cliente`/`Profesional` role rows, role-specific
  registration endpoints, all routers moved under `/api/v1`, and a substantially built
  out FastAdmin panel. `docs/auth.md` was updated for the new registration flow;
  `nextjs-frontend` was **not**.
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
1. Fix the Next.js registration flow for Cliente/Profesional (GitHub issue #7) — this
   is currently the biggest real gap, and blocks getting `pre-commit` fully green.
2. Implement email verification flow (GitHub issue #1).
3. Add `createsuperuser` management command under `commands/`.
4. If deploying: set Sentry env vars on Vercel (`SENTRY_ENVIRONMENT=production`)
   and add `SENTRY_AUTH_TOKEN` for frontend source maps; also add the repo secrets
   `ci.yml`/`pre-commit.yml` currently stub out locally, if real CI-time DB/JWT
   checks against production-like config are ever wanted (not required today).
5. Consider registering this repo on coveralls.io (currently not registered;
   `Coveralls` steps are `continue-on-error: true` as a result).
6. Continue evolving "busca oficio" domain features beyond Cliente/Profesional.

## Open considerations
- Whether to migrate MailHog → Mailpit.
- Whether `$PORT` / container deploy will ever be needed (not required for Vercel path).
- Product domain requirements past Cliente/Profesional not yet defined.
- No RBAC or fine-grained permissions — only binary `is_superuser` flag exists today.
- First real Sentry error from a running app has not been verified end-to-end
  via MCP yet.
- Webpack Server Actions are not auto-instrumented; we capture caught errors
  manually. `withServerActionInstrumentation()` is available if we want traces
  on those actions later.
- Whether the plain `POST /register` (fastapi-users base route, role-less) should be
  removed now that `/register/cliente` and `/register/profesional` exist, or kept for
  some other purpose (e.g. admin-created accounts) — currently it's just dead weight
  the frontend happens to still be calling incorrectly (issue #7).
