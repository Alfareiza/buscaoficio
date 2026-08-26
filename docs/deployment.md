# Deployment

Production runs on **AWS**: a single EC2 instance (Docker Compose) behind Caddy, backed by RDS Postgres, with images built in GitHub Actions and pushed to ECR.

```
GitHub Actions ──build──▶ ECR (buscaoficio-backend / buscaoficio-frontend, git-SHA tags)
        │
        └──deploy job──▶ EC2 (SSH): docker compose pull && up -d
                              │
                              ├─ Caddy: TLS (Let's Encrypt), app.buscaoficio.co → frontend, api.buscaoficio.co → backend
                              └─ backend ──asyncpg (SSL)──▶ RDS buscaoficio-1
```

The deployment operator's full knowledge base is the `aws-deployer` agent (`.claude/agents/aws-deployer.md`): resource IDs, verified facts, and runbooks. This file is the compact human-facing summary.

## CI/CD — `.github/workflows/deploy.yml`

Triggered on push to `main` / `18-deployment-workflow` (paths-filtered) or manually via `workflow_dispatch`:

1. **Build jobs** (parallel): assume the AWS role via GitHub OIDC, build the backend (`fastapi_backend/Dockerfile`) and frontend (`nextjs-frontend/Dockerfile.prod`) images with `--provenance=false` (see below), push both to ECR tagged with the commit SHA.
2. **Deploy job**: SSHes to the box, rewrites `BACKEND_IMAGE`/`FRONTEND_IMAGE` in `/opt/buscaoficio/.env`, then `docker compose pull && up -d` and prunes superseded images (the box has 8GB — pruning order matters, see the workflow comments).

Required GitHub **secrets**: `AWS_DEPLOY_ROLE_ARN`, `EC2_HOST`, `EC2_SSH_KEY` (`SENTRY_AUTH_TOKEN` optional — source-map upload only).

Notes from real operation:

- **If a push produces no run** (observed GitHub delivery flakiness): `gh workflow run "Deploy to production (EC2)" --ref <branch>`. `workflow_dispatch` reliably picks up the branch HEAD.
- **Concurrency guard** (`deploy-${{ github.ref }}`) serializes runs per ref — a duplicated push-event delivery can't race itself into immutable-tag collisions.
- **`--provenance=false` is load-bearing.** Without it buildx pushes an OCI index whose real layers sit in an *untagged* child manifest; the ECR lifecycle rule (expire untagged after 7 days) would strand the tag pointing at deleted content.
- **No migration step in the pipeline** — migrations are run manually (see below) and reviewed before applying, by project convention.

## On-box files (not in git)

Three env files live only on the EC2 box, at `/opt/buscaoficio/`:

| File | Contents |
| --- | --- |
| `.env` | `DOMAIN`, `API_DOMAIN`, `ACME_EMAIL`, `BACKEND_IMAGE`, `FRONTEND_IMAGE` (template: `.env.prod.example`) |
| `fastapi_backend/.env` | app config following `fastapi_backend/.env.example` |
| `nextjs-frontend/.env` | app config following `nextjs-frontend/.env.example` |

`Caddyfile` and `docker-compose.prod.yml` are **copied to the box manually** — editing them in git does not update production (documented in `deploy.yml` itself). `docker compose restart` does *not* pick up `env_file` changes; use `up -d` (recreates containers).

## First-time RDS setup

RDS enforces SSL (`rds.force_ssl=1`); both `app/database.py` and Alembic use asyncpg `ssl="prefer"`, so no URL flag is needed. `DATABASE_URL` is rebuilt from components — the query string is ignored, so don't rely on `?ssl=true`.

1. Reset/set the master password: `aws rds modify-db-instance --db-instance-identifier buscaoficio-1 --master-user-password <pw> --apply-immediately`
2. Create the app database: from the backend container, connect to the `postgres` maintenance DB and `CREATE DATABASE buscaoficio` (asyncpg one-liner — see the `aws-deployer` agent).
3. Fill `DATABASE_URL` plus the four `*_SECRET_KEY`s in `fastapi_backend/.env` (generate with `openssl rand -hex 32`). Empty secret keys mean tokens are signed with an empty string — check with `grep -E "^[A-Z_]+=$"`.
4. `docker compose -f docker-compose.prod.yml up -d backend` then `exec backend alembic upgrade head`.

## Post-deployment env checklist (backend)

| Var | Production value |
| --- | --- |
| `FRONTEND_URL` / `BACKEND_URL` | `https://app.buscaoficio.co` / `https://api.buscaoficio.co` |
| `CORS_ORIGINS` | `["https://app.buscaoficio.co"]` (never `["*"]` in prod) |
| `ADMIN_SESSION_COOKIE_SECURE` | `true` |
| `SENTRY_ENVIRONMENT` | `production` |

Email uses Hostinger SMTP (`MAIL_*` values identical to local dev). DNS: `app.` / `api.buscaoficio.co` are A records on Hostinger pointing at the EC2 Elastic IP; TLS is Caddy + Let's Encrypt, fully automatic.
