# Tech Context

## Overview by layer

### Frontend
- Next.js 16 (App Router) + React 19 + TypeScript
- Tailwind CSS + shadcn/ui (Radix) + Heroicons / Lucide
- Forms: react-hook-form + Zod
- API client: `@hey-api/openapi-ts` → `app/openapi-client` (axios adapter —
  returns `{...response, data}` on success, raw `AxiosError` with `.error`
  attached on failure)
- Package manager: **pnpm**
- Pages: `/login` and `/register` (share `app/(auth)/layout.tsx` route
  group + `components/auth/AuthCard.tsx` — passwordless email OTP, not a
  password form; `intent` prop differs the copy between the two),
  password recovery (vestigial — see `activeContext.md`), dashboard
  (list/add/delete items)
- Tests: Jest + Testing Library
- Auth helpers: `lib/auth-cookies.ts` (cookie forwarding/silent-refresh
  support), `lib/api-errors.ts` (`isUnauthorizedError`) — see
  `systemPatterns.md` § Frontend auth pattern (#10, merged to `main`)
- OTP auth: `components/actions/otp-auth-action.ts` (Server Actions),
  `components/auth/AuthCard.tsx` (the multi-step client component), split
  logo components in `components/ui/BuscaOficioLogo.tsx`
  (`BuscaOficioMark` svg-only, `BuscaOficioWordmark` text-only,
  `BuscaOficioLogo` composite) — see `systemPatterns.md` § Passwordless OTP
  auth pattern

### Backend
- FastAPI (async) + Uvicorn / Starlette
- Pydantic v2 + pydantic-settings
- Auth: fastapi-users (JWT + user CRUD) fronting a custom passwordless
  email-OTP flow (`app/otp_manager.py`) — password-based register/login
  routes were removed 2026-08-18; verify/reset routes remain but are
  vestigial. See `systemPatterns.md` § Passwordless OTP auth pattern.
- Domain API: Items CRUD + fastapi-pagination
- Email: fastapi-mail + templates (`otp_code.html`, `password_reset.html`); local SMTP via MailHog
- Python 3.12, deps via **uv**
- Tests: pytest / pytest-asyncio, coverage → Coveralls

### Database
- PostgreSQL 17 (Docker)
- SQLAlchemy 2 + asyncpg
- Migrations: Alembic (async)
- Models: `User` (UUID, fastapi-users) ↔ `Item` (name, description, quantity, FK user, cascade delete); `RefreshToken` (hash, fingerprint hash, expiry, revoked_at, FK user — merged to `main`, see `systemPatterns.md` § JWT refresh token rotation); `EmailOtp` (`email_otps` table, migration `a067ad066d81` — `email`, `code_hash`, `attempts`, `expires_at`, `consumed_at`, `created_ip`; keyed by email, not `user_id`, since the account may not exist yet — see `systemPatterns.md` § Passwordless OTP auth pattern)
- Separate test DB: `db_test`
- Engine uses **NullPool** (serverless / Vercel friendly)

### Local host ports (customized for this machine)
| Service | Host port | Container port |
|---------|-----------|----------------|
| Postgres `db` | **5434** | 5432 |
| Postgres `db_test` | **5435** | 5432 |
| Backend API | **8001** | 8001 |
| Frontend | 3000 | 3000 |
| MailHog SMTP | 1025 | 1025 |
| MailHog UI | 8025 | 8025 |

Changed from defaults (Postgres 5432/5433, API 8000) to avoid conflict with another local project.

### DevOps / Infrastructure
- Docker Compose: `backend`, `frontend`, `db`, `db_test`, `mailhog`
- Shared volume `local-shared-data` for OpenAPI schema between BE and FE containers
- Makefile for start, migrate, test, shells
- GitHub Actions: CI (FastAPI + Next.js), pre-commit, release
- Deploy target: **Vercel** (separate FE/BE projects; prod deploy workflow files at repo root, move into `.github/workflows` to enable)
- Quality: pre-commit, Ruff, mypy, ESLint/Prettier
- Docs: MkDocs Material

### Production SSH access
- Two SSH keys authorize into EC2 `i-0b3ac8e7768cb4b5d` (`ec2-user`,
  Elastic IP `44.207.170.68`), each scoped to a different purpose:
  - **Operator key** — `~/.ssh/aag.pem` (key pair name `aag`), full admin
    access, used for manual ops (this file, deploys, debugging). Not
    rotated as part of this procedure.
  - **Deploy-only key** — used exclusively by the `deploy` job in
    `.github/workflows/deploy.yml`, which SSHes in to rewrite
    `BACKEND_IMAGE`/`FRONTEND_IMAGE` in `/opt/buscaoficio/.env` and run
    `docker compose -f docker-compose.prod.yml pull && up -d`. It needs no
    other permissions on the box. Stored solely as the `EC2_SSH_KEY`
    GitHub Actions secret — never committed to the repo, never printed to
    a terminal/transcript other than the user's own when first generated.
- **Rotation procedure** (same steps used 2026-08-22, see below):
  1. Generate a new ed25519 keypair locally, e.g.
     `ssh-keygen -t ed25519 -f /tmp/buscaoficio_deploy_key_new -N "" -C "github-actions-deploy@buscaoficio"`.
  2. SSH in with the personal `aag` key and swap the line in
     `~/.ssh/authorized_keys`: remove the old line tagged
     `github-actions-deploy@buscaoficio`, append the new public key.
     Leave the `aag` line untouched.
  3. Update the `EC2_SSH_KEY` GitHub Actions secret with the new private
     key contents.
  4. Verify: SSH in with the new private key and confirm it authenticates
     (e.g. `ssh -i <new-key> ec2-user@44.207.170.68 whoami`); trigger or
     wait for the next `deploy.yml` run to confirm CI/CD still works.
  5. Securely delete the old local private key file and, once the GitHub
     secret is confirmed updated, the new key's local copies too — the
     key should live only in the GitHub secret and on the box's
     `authorized_keys`, not on any operator's disk long-term.
- 2026-08-22: the deploy-only key was rotated because the previous one had
  been accidentally exposed in an agent transcript during an earlier
  session (see memory `project_aws_deployment.md` for the incident, not
  duplicated here).

## E2E type safety
Not “E2W”. End-to-end type safety means:
1. FastAPI routes + Pydantic → OpenAPI schema
2. Frontend openapi-ts generates typed TS client
3. Compile-time alignment FE ↔ BE when schema regenerates

## MailHog
- Fake local SMTP catcher; captures mail for password reset / verification in UI (`:8025`)
- Community: still useful and simple; **unmaintained since ~2020**; for greenfield, prefer **Mailpit** (drop-in same ports)

## Vercel vs Docker (important)
- **Local:** Docker containers / Compose
- **Vercel:** NOT containers - serverless (Next.js + FastAPI via `api/index.py` importing `app`)
- **`$PORT` is not mapped** for Vercel in this repo. Local `start.sh` hardcodes `--port 8001`. On Vercel the platform invokes ASGI; no uvicorn bind.
- Dockerfiles / EXPOSE are for local Compose, not Vercel.

## Observability
- Org: `aag-k0`. Projects: `buscaoficio-backend` (python-fastapi),
  `buscaoficio-frontend` (javascript-nextjs). Team slug: `aag`.
- Signals: errors + tracing + logs. No Session Replay / profiling unless decided later.
- Backend: `sentry-sdk[fastapi]`; init in `app/main.py` if `SENTRY_DSN` is set.
  Logger: `from app.config import logger`. Sample rate 1.0 unless
  `SENTRY_ENVIRONMENT=production` (then 0.1).
- Frontend: `@sentry/nextjs`. Official files only (see `systemPatterns.md`).
  Sample rate via `NODE_ENV` (1.0 development, 0.1 otherwise).
- This app uses **Webpack** (`next dev --webpack` / `next build --webpack`),
  not Turbopack. Webpack does **not** auto-instrument Server Actions.
- Local DSNs live in `fastapi_backend/.env` and `nextjs-frontend/.env.local`
  (gitignored). `.env.example` has empty placeholders only.
- Tests: backend skips Sentry when `pytest` is in `sys.modules`. Frontend
  tests do not mock Sentry globally.

## Key env vars (backend)
- `DATABASE_URL`, `TEST_DATABASE_URL`
- `ACCESS_SECRET_KEY`, `RESET_PASSWORD_SECRET_KEY`, `VERIFICATION_SECRET_KEY`
- `ACCESS_TOKEN_EXPIRE_SECONDS` (default 900 = 15 min, was 3600),
  `REFRESH_TOKEN_EXPIRE_SECONDS` (default 2592000 = 30 days, new) — see
  `systemPatterns.md` § Auth pattern for the refresh-token-rotation flow
- `REGISTRATION_TOKEN_SECRET_KEY` (signs the short-lived token proving OTP
  ownership between `/otp/verify` and `/register/*/otp`),
  `OTP_CODE_EXPIRE_SECONDS` (default 600 = 10 min),
  `REGISTRATION_TOKEN_EXPIRE_SECONDS` (default 900 = 15 min) — see
  `systemPatterns.md` § Passwordless OTP auth pattern
- `OPENAPI_OUTPUT_FILE`
- `CORS_ORIGINS`, `FRONTEND_URL`
- Mail settings (`MAIL_*`)
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT` (optional; empty DSN disables Sentry)
- FastAdmin: `ADMIN_USER_MODEL`, `ADMIN_USER_MODEL_USERNAME_FIELD`,
  `ADMIN_SECRET_KEY`, `ADMIN_SITE_NAME`, `ADMIN_SITE_HEADER_LOGO`,
  `ADMIN_SITE_SIGN_IN_LOGO`, `ADMIN_SESSION_COOKIE_SECURE=false` (local HTTP).
  Logo values are URL paths under `/static`, served from `app/static/`.

## Key env vars (frontend)
- `API_BASE_URL`, `OPENAPI_OUTPUT_FILE`
- `NEXT_PUBLIC_SENTRY_DSN` (browser)
- `SENTRY_DSN` (server / edge)
- `SENTRY_AUTH_TOKEN` (build-time source maps; not set locally yet)
