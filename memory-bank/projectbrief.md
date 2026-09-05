# Project Brief - Buscaoficio

## Origin
This repo is based on Vinta Software’s **Next.js FastAPI Template** (`vintasoftware/nextjs-fastapi-template`). It is a full-stack starter with auth, a dashboard, and end-to-end typed API clients - not yet a domain-specific “busca oficio” product.

## Goals
- Provide a production-shaped MVP foundation (auth + CRUD + typed FE/BE contract).
- Keep frontend and backend in sync via OpenAPI-generated TypeScript clients.
- Support local Docker Compose development and production deploy to **Vercel**
  (frontend) + a managed backend host (Railway / Render / Fly.io — TBD).
  EC2 + ECR + RDS were retired 2026-09-05; branch `ec2` preserves that
  configuration. Prod Postgres remains on Supabase.

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
- Returning to EC2 + ECR until the product is ready for launch (see
  branch `ec2` for the preserved configuration).

## Source of truth
- Product intent and current focus: `memory-bank/activeContext.md` and `progress.md`.
- Stack and constraints: `techContext.md`.
- Architecture patterns: `systemPatterns.md`.
