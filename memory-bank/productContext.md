# Product Context

## Why this project exists
The template gives a clean, typed full-stack starting point so product work can begin without reinventing auth, API contracts, or deploy plumbing.

## Problems it solves
- FE/BE schema drift → OpenAPI + generated TS client.
- Auth boilerplate → fastapi-users (JWT) fronting a passwordless email-OTP
  login/registration flow (see `memory-bank/systemPatterns.md` § Passwordless
  OTP auth pattern); password-based register/verify/reset routes remain in
  the codebase but are vestigial as of 2026-08-18.
- Local email testing without sending real mail → MailHog.
- Consistent local environments → Docker Compose + Makefile.

## How it should work
1. Backend exposes FastAPI routes and Pydantic models; OpenAPI schema is generated.
2. Frontend regenerates a typed client from that schema.
3. Users authenticate and manage items via the Next.js dashboard.
4. Schema changes to Postgres go through Alembic migrations (explicit, not automatic on model edit).
5. Unhandled errors, traces, and app logs go to Sentry when a DSN is set; local without DSN stays silent.

## UX goals
- Immediate usable auth + dashboard after setup.
- Developer experience: hot reload + automatic client sync when API surfaces change.
- Clear separation: Docker Compose for local infra; production is the
  same Compose shape on EC2 (`docker-compose.prod.yml`), with images
  built in GitHub Actions and stored in ECR — not Docker-on-Vercel.
  Template Vercel files still exist but are not the prod path.
