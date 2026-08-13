# Product Context

## Why this project exists
The template gives a clean, typed full-stack starting point so product work can begin without reinventing auth, API contracts, or deploy plumbing.

## Problems it solves
- FE/BE schema drift → OpenAPI + generated TS client.
- Auth boilerplate → fastapi-users (JWT, register, verify, reset).
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
- Clear separation: Docker for local infra; Vercel serverless for target deploy (not Docker-on-Vercel).
