# Project Brief - Buscaoficio

## Origin
This repo is based on Vinta Software’s **Next.js FastAPI Template** (`vintasoftware/nextjs-fastapi-template`). It is a full-stack starter with auth, a dashboard, and end-to-end typed API clients - not yet a domain-specific “busca oficio” product.

## Goals
- Provide a production-shaped MVP foundation (auth + CRUD + typed FE/BE contract).
- Keep frontend and backend in sync via OpenAPI-generated TypeScript clients.
- Support local Docker Compose development and Vercel deployment.

## Scope (current template)
- JWT authentication (register, login, verify, password reset).
- User management via fastapi-users.
- Items CRUD with pagination behind an authenticated dashboard.
- Docs via MkDocs Material.
- Observability: Sentry (errors + tracing + logs) on FastAPI and Next.js.

## Out of scope (for now)
- Domain-specific “busca oficio” business features.
- Production email provider configuration beyond local MailHog.
- Non-Vercel production container orchestration (unless explicitly adopted later).

## Source of truth
- Product intent and current focus: `memory-bank/activeContext.md` and `progress.md`.
- Stack and constraints: `techContext.md`.
- Architecture patterns: `systemPatterns.md`.
