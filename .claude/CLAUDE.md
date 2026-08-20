# Overview

Buscaoficio is a monorepo full-stack app built on Vinta Software's Next.js + FastAPI template: a Next.js (App Router, TypeScript) frontend talking to a FastAPI (async, Python) backend through an OpenAPI-generated typed client, backed by PostgreSQL. The domain-specific "busca oficio" product itself isn't built yet — this is still the auth + CRUD template foundation (see `memory-bank/projectbrief.md`).

The project is indexed through code-memory-mcp located in @memory-bank folder and the memory bank store the context, progress and detailed information. `memory-bank/techContext.md` and `memory-bank/systemPatterns.md` hold the deepest architectural detail; this file and the frontend/backend files below are the fast-recall summary for a new session.

## Stack at a glance

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + TypeScript, Tailwind + shadcn/ui, Server Actions — see `nextjs-frontend/.CLAUDE.md` |
| Backend | FastAPI (async) + Pydantic v2, fastapi-users, SQLAlchemy 2 + asyncpg — see `fastapi_backend/.CLAUDE.md` |
| Database | PostgreSQL 17, Alembic migrations |
| FE↔BE contract | `@hey-api/openapi-ts` generates a typed TS client from the backend's OpenAPI schema (dev-only watcher keeps it in sync) |
| Auth | Passwordless email OTP + JWT access/refresh token rotation — detailed in both files below, full write-up in `docs/auth.md` |
| Observability | Sentry (errors + tracing + logs) on both sides |

## Rules

- Never make assumptions when important information is missing
- When a message starts with "Q:" or "?", provide analysis/opinion only. Do NOT make any code changes, file edits, or tool calls. Just answer the question.
- Review outputs before final delivery

## Frontend

@nextjs-frontend/.CLAUDE.md

### Guidelines for frontend

- Use the playwright skill when you wanna run integrations tests or double check some UI component or the page in general
- Since this project is using next.js. Use the nextjs skills to make the code better, simple and high quality

## Backend

@fastapi_backend/.CLAUDE.md
