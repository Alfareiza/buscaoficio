# Deployment

**Active production is Vercel** (Hobby team `alfareizas-projects`). Postgres is
**Supabase** (transaction-mode pooler `:6543`). TLS and hostname routing are
Vercel’s. The EC2 + ECR + Caddy stack was retired 2026-09-05; restore it from
branch `ec2` using
[`docs/ec2-recovery.md`](https://github.com/Alfareiza/buscaoficio/blob/ec2/docs/ec2-recovery.md)
on that branch. `Caddyfile` and `infra-manual-reminder.yml` live **only** there.

```
GitHub (Alfareiza/buscaoficio)
        │  git push / PR
        ▼
Vercel  ├─ buscaoficio-front  (root: nextjs-frontend/)  → https://app.buscaoficio.co
        └─ buscaoficio-back   (root: fastapi_backend/,
                               ASGI api/index.py)        → https://api.buscaoficio.co
                    │
                    └── asyncpg ──▶ Supabase pooler :6543
```

Local development is unchanged: Docker Compose + Makefile. Production images
(`Dockerfile`, `Dockerfile.prod`) are unused while Vercel is the host.

## Vercel projects

| Project | Root | Framework | Production URL |
| --- | --- | --- | --- |
| `buscaoficio-front` | `nextjs-frontend/` | Next.js 16 (Node 20) | `https://app.buscaoficio.co` |
| `buscaoficio-back` | `fastapi_backend/` | Python 3.12 ASGI (`api/index.py`) | `https://api.buscaoficio.co` |

Git integration deploys **production** from `main` once this branch is merged.
PRs get preview URLs (`*.vercel.app`). `CORS_ORIGIN_REGEX` on the backend
allows `https://buscaoficio-front.*\.vercel\.app`.

`output: "standalone"` is **not** set in `next.config.mjs` on this branch
(Docker/EC2 only; restore it from `ec2`).

## Env vars (dashboard, not git)

Backend (`buscaoficio-back`): `DATABASE_URL` (Supabase pooler, Production **and**
Preview), `FRONTEND_URL=https://app.buscaoficio.co`,
`BACKEND_URL=https://api.buscaoficio.co`, `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`,
auth secrets, `GOOGLE_OAUTH_*`, `MAIL_*`, `ADMIN_*`, `SENTRY_DSN`,
`SENTRY_ENVIRONMENT=production`.

Frontend (`buscaoficio-front`): `API_BASE_URL=https://api.buscaoficio.co`,
`SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`, optional `SENTRY_AUTH_TOKEN` (source maps).

Vercel injects env at **deploy** time. After adding or changing a variable,
create a new deployment (git push or Redeploy). Existing lambdas keep the old snapshot.

## Database migrations

`.github/workflows/migrate.yml` runs `uv run alembic upgrade head` on GitHub
Actions with secret `DATABASE_URL`. It does not SSH to EC2.

Engine connect args (`ASYNC_CONNECT_ARGS` in `app/database.py`) stay: caches
off + unnamed prepares for PgBouncer. Do not rely on `?ssl=` / `?pgbouncer=`
in the URL.

## DNS

Hostinger zone for `buscaoficio.co` (`*.dns-parking.com` nameservers).
Production records:

| Name | Type | Target |
| --- | --- | --- |
| `app` | A | `76.76.21.21` (Vercel) |
| `api` | A | `76.76.21.21` (Vercel) |

CNAME to `cname.vercel-dns.com` is also valid. TLS is Vercel-managed.

## Google Sign-In

`redirect_uri` is `{BACKEND_URL}/api/v1/auth/google/callback`. Do **not**
change the Google Cloud Console URI while `BACKEND_URL` stays
`https://api.buscaoficio.co` — the hostname is the same whether Caddy or
Vercel answers it. JS origin stays `https://app.buscaoficio.co`.

## GitHub Actions

| Workflow | Role on this branch |
| --- | --- |
| `ci.yml` | Tests; `requirements.txt` staleness check |
| `migrate.yml` | Alembic via `uv` + `DATABASE_URL` secret |
| `deploy.yml` | **Disabled** (EC2). Live copy on branch `ec2` |

GitHub user for this repo: **Alfareiza** (not `alfonsorevin`).
