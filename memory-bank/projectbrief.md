# Project Brief - Buscaoficio

## Origin
This repo is based on Vinta Software’s **Next.js FastAPI Template** (`vintasoftware/nextjs-fastapi-template`). It is a full-stack starter with auth, a dashboard, and end-to-end typed API clients - not yet a domain-specific “busca oficio” product.

## Goals
- Provide a production-shaped MVP foundation (auth + CRUD + typed FE/BE contract).
- Keep frontend and backend in sync via OpenAPI-generated TypeScript clients.
- Support local Docker Compose development and production deploy to EC2
  (GitHub Actions → ECR → Docker Compose on the box). Prod schema via a
  separate migrate Action, not bundled into deploy. Prod Postgres is
  temporarily Supabase; switch to RDS after launch.

## Scope (current template)
- JWT authentication — passwordless email OTP for login/registration (the
  only linked flow since 2026-08-18), refresh token rotation with a
  double-submit fingerprint cookie. Password-based login/register were
  removed; password reset/email verification remain but are vestigial.
- User management via fastapi-users.
- Items CRUD with pagination behind an authenticated dashboard.
- Docs via MkDocs Material.
- Observability: Sentry (errors + tracing + logs) on FastAPI and Next.js.

## Out of scope (for now)
- Domain-specific “busca oficio” business features.
- Production email provider configuration beyond local MailHog.
- Vercel serverless as the production path (template leftovers remain;
  production is EC2 + ECR, see `techContext.md`).

## Source of truth
- Product intent and current focus: `memory-bank/activeContext.md` and `progress.md`.
- Stack and constraints: `techContext.md`.
- Architecture patterns: `systemPatterns.md`.
