# Project Brief - Buscaoficio

## Origin
This repo started from Vinta Software’s **Next.js FastAPI Template** (`vintasoftware/nextjs-fastapi-template`) — a full-stack starter with auth, a dashboard, and end-to-end typed API clients. As of 2026-08-14, domain work has begun: the template's generic `User` model has been split into `Usuario` + `Cliente`/`Profesional` role rows (see `systemPatterns.md` → "Cliente/Profesional domain model"). It is no longer purely a template baseline.

## Goals
- Provide a production-shaped MVP foundation (auth + CRUD + typed FE/BE contract).
- Keep frontend and backend in sync via OpenAPI-generated TypeScript clients.
- Support local Docker Compose development and Vercel deployment.
- Model the "busca oficio" domain: clients (`Cliente`) who need work done, and professionals (`Profesional`) who offer it, sharing one `Usuario` identity.

## Scope (current)
- JWT authentication (register, login, verify, password reset), plus role-specific
  registration: `POST /api/v1/auth/register/cliente` and `/register/profesional`
  (each creates the `Usuario` + role row in one transaction).
- User management via fastapi-users; `Cliente`/`Profesional` shared-PK composition on `usuario_id`.
- FastAdmin panel for `Usuario`/`Cliente`/`Profesional` (create/edit linked records, inline role attachment).
- Items CRUD with pagination behind an authenticated dashboard (template leftover, not yet domain-relevant).
- Docs via MkDocs Material.
- Observability: Sentry (errors + tracing + logs) on FastAPI and Next.js.
- Dedicated GitHub Actions workflow (`migrate.yml`) to run Alembic migrations against
  production on demand — see `techContext.md` → "CI/CD workflows".

## Out of scope (for now)
- Further "busca oficio" business features beyond the Cliente/Profesional split (matching, listings, payments, etc.).
- Production email provider configuration beyond local MailHog.
- Non-Vercel production container orchestration (unless explicitly adopted later).

## Known gap
- The Next.js registration form/action was never updated for the new `nombre_completo`-required
  `UserCreate` schema (or for the `/register/cliente` vs `/register/profesional` split) — see
  GitHub issue [#7](https://github.com/Alfareiza/buscaoficio/issues/7) and `activeContext.md`.

## Source of truth
- Product intent and current focus: `memory-bank/activeContext.md` and `progress.md`.
- Stack and constraints: `techContext.md`.
- Architecture patterns: `systemPatterns.md`.
