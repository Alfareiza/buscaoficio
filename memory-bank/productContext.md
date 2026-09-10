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
4. Schema changes to Postgres go through Alembic (explicit, not automatic
   on model edit). Local: Makefile/`make docker-migrate-db`. Production
   (Supabase): `.github/workflows/migrate.yml` runs Alembic on GitHub
   Actions with secret `DATABASE_URL`, kept separate from Vercel deploys.
5. Unhandled errors, traces, and app logs go to Sentry when a DSN is set; local without DSN stays silent.
6. Domain tables land **one domain at a time** from the ER dictionary
   (not one-shot). First slice: **Catálogo** — service categories, zones,
   and profesional N:M links; public read API for evaluation. Registration
   does not yet write `zona_id` or N:M rows (follow-up onboarding).

## UX goals
- Immediate usable auth + dashboard after setup.
- Signup role choice (cliente vs profesional) reads as one question,
  not two competing cards.
- Auth shell (`/login`, `/register`) shows a rotating sample of oficios
  on the brand panel so the product reads as a trades marketplace, not
  a generic template.
- Developer experience: hot reload + automatic client sync when API surfaces change.
- Clear separation: Docker Compose for local infra; production is
  Vercel (two projects) + Supabase. EC2/Compose restore: branch `ec2`.
