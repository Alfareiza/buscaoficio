# Active Context

## Current focus
- FastAdmin branding (site name + logo) is wired; next product work is still
  auth gaps (email verification) unless we deploy and wire Vercel env vars.
- Auth system understanding, documentation, and gap identification.

## Recent changes
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
1. Implement email verification flow (GitHub issue #1).
2. Add `createsuperuser` management command under `commands/`.
3. If deploying: set Sentry env vars on Vercel (`SENTRY_ENVIRONMENT=production`)
   and add `SENTRY_AUTH_TOKEN` for frontend source maps.
4. Decide whether to evolve toward domain "busca oficio" features.

## Open considerations
- Whether to migrate MailHog → Mailpit.
- Whether `$PORT` / container deploy will ever be needed (not required for Vercel path).
- Product domain requirements not yet defined beyond the template MVP.
- No RBAC or fine-grained permissions — only binary `is_superuser` flag exists today.
- First real Sentry error from a running app has not been verified end-to-end
  via MCP yet.
- Webpack Server Actions are not auto-instrumented; we capture caught errors
  manually. `withServerActionInstrumentation()` is available if we want traces
  on those actions later.
