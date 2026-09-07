# EC2 recovery checklist

Created 2026-09-07 so a later session can restore AWS production without
re-deriving it. **This branch is not live.** Live production on that date was
Vercel (`buscaoficio-front` + `buscaoficio-back`) with Hostinger A records
`app` / `api` → `76.76.21.21`. Postgres is **Supabase** (transaction pooler
`:6543`). RDS `buscaoficio-1` and EC2 `i-0b3ac8e7768cb4b5d` were deleted
2026-09-05.

Do not SSH to `44.207.170.68`. That Elastic IP is dead. Do not treat any ID
below as still allocated — re-verify with `AWS_PROFILE=personal` in `us-east-1`.

Operator knowledge that used to live only in `.claude/agents/aws-deployer.md`
(gitignored) is folded in here.

---

## 0. Decide the cutover, then freeze Vercel

- [ ] Confirm you actually want DNS + traffic on EC2 again (charges resume).
- [ ] Prefer **keeping Supabase** as `DATABASE_URL` unless you explicitly
      recreate RDS. The app engine (`ASYNC_CONNECT_ARGS` in `app/database.py`)
      already works on the pooler. Recreating RDS is extra cost and a data
      copy.
- [ ] On Vercel: pause both projects or remove the `app.buscaoficio.co` /
      `api.buscaoficio.co` domains **after** Caddy has valid certs on the new
      box (not before, or you have an HTTPS gap).
- [ ] GitHub user for this repo is **Alfareiza** (id `63620799`), not
      `alfonsorevin`.

---

## 1. Code: do not deploy this snapshot as-is

`ec2` froze **2026-09-05**. Product and Vercel work landed on `main` /
`28-vercel-deployment` after that (OTP polish, Sentry, proxy/logout, Alembic
inlining, CORS regex, etc.).

- [ ] `git fetch origin`
- [ ] Merge `origin/main` into `ec2` (or rebase — expect conflicts).
- [ ] Conflicts you must resolve **toward EC2**, not Vercel:
  - `nextjs-frontend/next.config.mjs` — keep `output: "standalone"` (required
    by `Dockerfile.prod`).
  - `.github/workflows/deploy.yml` — keep the **push** trigger. Retarget
    `on.push.branches` to the branch you will actually push (`ec2` or `main`
    after cutover). The frozen file still says `main`.
  - `.github/workflows/migrate.yml` — EC2 era SSHes into the box and runs
    Alembic **inside** the backend container. Do not keep the Vercel-era
    `uv run alembic` job unless you deliberately want Actions to talk to
    Supabase directly (that also works; pick one).
  - **`Caddyfile` — keep ours.** `main` / `28-vercel-deployment` **deleted**
    it (Vercel terminates TLS). Without this file the box has no HTTPS and
    no `app.` / `api.` routing. See § 1a.
  - **`.github/workflows/infra-manual-reminder.yml` — keep ours.** Same
    deletion on `main`. See § 1a. Re-enable its push trigger so a Caddyfile
    or `docker-compose.prod.yml` edit fails CI until someone copies the
    file onto `/opt/buscaoficio`.
- [ ] Vercel-only files can stay unused: `fastapi_backend/api/index.py`,
      `*/vercel.json`, `fastapi_backend/requirements.txt`. They do not break
      Docker.
- [ ] Confirm `nextjs-frontend/Dockerfile.prod` still uses the standalone
      output (`HOSTNAME=0.0.0.0`, `PORT=3000`).

### 1a. Why `Caddyfile` and `infra-manual-reminder.yml` stay on this branch

Vercel does TLS and hostname routing (`app.buscaoficio.co` /
`api.buscaoficio.co`). Those two files do nothing there, so they were
removed from `28-vercel-deployment` / `main` on 2026-09-07. They are
**load-bearing on EC2**. If a merge from `main` deletes them, stop and
restore from this branch (`git checkout HEAD -- Caddyfile
.github/workflows/infra-manual-reminder.yml`).

**`Caddyfile` (repo root, copied to `/opt/buscaoficio/Caddyfile`)**

- Only process that publishes **80/443** on the box. Compose bind-mounts
  it into `caddy:2-alpine` (`docker-compose.prod.yml`).
- Terminates TLS via Let’s Encrypt (`ACME_EMAIL` in `/opt/buscaoficio/.env`).
  There is no Route 53 and no ACM. If this file is missing, DNS can point
  at the EIP and browsers still fail HTTPS.
- Routes `DOMAIN` → frontend container and `API_DOMAIN` → backend
  container. FastAdmin is `/admin` on FastAPI, so the backend **must**
  have its own public hostname. Caddy does not path-split, so Next
  `/api/auth/google/complete` and FastAPI `/api/v1/auth/google/*` never
  collide.
- A bind-mount change does **not** recreate the container. After you
  `scp` a new Caddyfile: `caddy reload --config /etc/caddy/Caddyfile
  --adapter caddyfile`.
- `deploy.yml` never SCPs this file (`824f2f1`). Editing it in git does
  not update the box.

**`.github/workflows/infra-manual-reminder.yml`**

- Intentionally **fails CI** when `Caddyfile` or `docker-compose.prod.yml`
  changes, because those files are copied by hand. Without the reminder,
  a merge looks green and production still runs the old Caddy/compose.
- Not used under Vercel (no box to copy onto). Keep the workflow on
  `ec2`; do not take the delete from `main`.
- After restore, the push trigger must be on again (the Vercel-era copy
  was `workflow_dispatch` only).

---

## 2. What used to exist (re-verify, then recreate)

Account `502993831706`, region `us-east-1`, CLI profile **`personal`**
(`export AWS_PROFILE=personal`). Stale profile `aeprod` has no access.

| Resource | Last known ID | Notes |
| --- | --- | --- |
| EC2 | `i-0b3ac8e7768cb4b5d` | `t3.micro`, Amazon Linux **2023** (`dnf`, not `apt`), ~913MB RAM, 8GB disk. **Never build images on the box.** |
| Elastic IP | `44.207.170.68` | Allocate a **new** EIP; the old one is gone. |
| RDS | `buscaoficio-1` | `db.t4g.micro`, Postgres 18.3, not public, `rds.force_ssl=1`. Deleted. Skip if staying on Supabase. |
| EC2 SG | `sg-039c4a5087150e43b` | 22/80/443. Port 22 was `0.0.0.0/0` so GitHub `ssh-action` could reach the box (`PasswordAuthentication no`). Do not silently re-narrow without asking. |
| RDS SG | `sg-0be80f37b50452326` | 5432 **only** from the EC2 SG. |
| Instance profile | `buscaoficio-ec2-ecr-pull` | ECR pull; no stored Docker creds on the box. |
| OIDC role | `buscaoficio-github-actions-deploy` | GitHub Actions → ECR push. Secret `AWS_DEPLOY_ROLE_ARN`. |
| OIDC `sub` | `repo:Alfareiza@63620799/buscaoficio@1329243606:*` | **Numeric IDs, not slugs.** `repo:Alfareiza/buscaoficio:…` fails AssumeRole. Repo IDs do not change when you create a new instance. |
| ECR | `buscaoficio-backend`, `buscaoficio-frontend` | Registry `502993831706.dkr.ecr.us-east-1.amazonaws.com`. SHA tags, **immutable**, `--provenance=false`, prune **after** `up -d` with `-a`. |
| SSH operator | `~/.ssh/aag.pem` (key pair name `aag`) | `ec2-user`. Recreate the key pair in AWS if it was deleted with the instance. |
| Deploy key | GitHub secret `EC2_SSH_KEY` | ed25519, comment `github-actions-deploy@buscaoficio`. Put the public half in `authorized_keys` on the new box. Never print the private key. |

Leftover ECR repo `buscaoficio-aws-repo` was unused. Ignore it.

---

## 3. Provision the box

- [ ] One instance only (free-tier 750 hrs). Do not split FE/BE across two micros.
- [ ] Amazon Linux 2023, `t3.micro`, x86_64 (GitHub runners match; a Mac arm64
      local image will `exec format` on the box).
- [ ] Attach instance profile `buscaoficio-ec2-ecr-pull` (recreate the role if
      it was deleted).
- [ ] SG: 80/443 world; 22 as before (world **or** SSM — see aws-deployer notes).
- [ ] Allocate + associate a new Elastic IP. Record it.
- [ ] Disk 8GB fills fast. `deploy.yml` must prune **after** `up -d`.
- [ ] `sudo mkdir -p /opt/buscaoficio` and own it as `ec2-user`.
- [ ] Install Docker + Compose plugin. Do not install a compiler toolchain
      for app builds.

---

## 4. Files that live only on the box (never git)

Copy from this repo, then fill secrets by hand:

```
/opt/buscaoficio/docker-compose.prod.yml
/opt/buscaoficio/Caddyfile
/opt/buscaoficio/.env                 # from .env.prod.example
/opt/buscaoficio/fastapi_backend/.env
/opt/buscaoficio/nextjs-frontend/.env
```

GitHub Actions does **not** SCP compose/Caddy (`824f2f1`). After you edit
those files in git, copy them yourself. That is why
`infra-manual-reminder.yml` exists (see § 1a). A green CI run does **not**
mean the box has the new Caddyfile.

### `/opt/buscaoficio/.env` (compose + Caddy)

```
DOMAIN=app.buscaoficio.co
API_DOMAIN=api.buscaoficio.co
ACME_EMAIL=buscaoficio.co@gmail.com
BACKEND_IMAGE=502993831706.dkr.ecr.us-east-1.amazonaws.com/buscaoficio-backend:<sha>
FRONTEND_IMAGE=502993831706.dkr.ecr.us-east-1.amazonaws.com/buscaoficio-frontend:<sha>
```

`deploy.yml` rewrites the two `*_IMAGE` lines. Never `:latest`.

### App env that **must** differ from local Docker

| Var | Production |
| --- | --- |
| `DATABASE_URL` | Supabase pooler `:6543` (recommended) or new RDS with TLS. No `?ssl=` / `?pgbouncer=` query flags — `ASYNC_CONNECT_ARGS` in code. |
| `FRONTEND_URL` | `https://app.buscaoficio.co` |
| `BACKEND_URL` | `https://api.buscaoficio.co` |
| `CORS_ORIGINS` | `["https://app.buscaoficio.co"]` |
| `ADMIN_SESSION_COOKIE_SECURE` | `true` |
| `SENTRY_ENVIRONMENT` | `production` |
| frontend `API_BASE_URL` | `https://api.buscaoficio.co` |

Keep real `*_SECRET_KEY`s, `GOOGLE_OAUTH_*`, Hostinger `MAIL_*`
(`smtp.hostinger.com:465`). AWS blocks outbound **25**; **465** is fine.
MailHog is not a prod container.

`docker compose restart` does **not** reload `env_file`. Use `up -d`.

---

## 5. GitHub secrets + IAM

Secrets (not variables): `AWS_DEPLOY_ROLE_ARN`, `EC2_HOST` (new EIP),
`EC2_SSH_KEY`.

- [ ] Confirm OIDC provider `token.actions.githubusercontent.com` still exists.
- [ ] Confirm role trust `sub` uses **numeric** repo IDs (table above).
- [ ] `EC2_HOST` = new EIP. `deploy.yml` SSH user is `ec2-user`.
- [ ] Optional: `SENTRY_AUTH_TOKEN` (source maps only). Runtime uses `SENTRY_DSN`.

---

## 6. First deploy

- [ ] Push to the branch `deploy.yml` watches, or `workflow_dispatch`.
- [ ] Builds use `--provenance=false`. Tag = `github.sha`. Immutable ECR:
      a re-run of the same SHA must treat “tag already exists” as success
      (already in this branch’s `deploy.yml`).
- [ ] Deploy job: rewrite `*_IMAGE` in `/opt/buscaoficio/.env`, then
      `docker compose -f docker-compose.prod.yml pull && up -d`, then
      `caddy reload`.
- [ ] Concurrency group `deploy-${{ github.ref }}`, `cancel-in-progress: false`.
- [ ] If a push creates **zero** workflow runs, dispatch manually — GitHub
      has dropped push events on this repo before.

Stack on `app_network`: backend (`fastapi run … --workers 2`), frontend
(`pnpm start` / standalone), Caddy `caddy:2-alpine`. Only Caddy publishes
80/443.

---

## 7. DNS + TLS (the actual cutover)

Hostinger zone, nameservers `*.dns-parking.com`. No Route 53, no ACM.

While Vercel is live:

| Name | Type | Target |
| --- | --- | --- |
| `app` | A | `76.76.21.21` |
| `api` | A | `76.76.21.21` |

- [ ] Point **both** A records at the **new EIP**.
- [ ] Wait for TTL. Caddy issues Let’s Encrypt only when 80/443 reach **this**
      box.
- [ ] `https://app.buscaoficio.co/login` → 200.
- [ ] `https://api.buscaoficio.co/docs` → 200.
- [ ] FastAdmin `https://api.buscaoficio.co/admin` (backend is public on
      purpose).
- [ ] Then detach custom domains on Vercel so certs/DNS do not fight.

Google Sign-In: `redirect_uri` is
`{BACKEND_URL}/api/v1/auth/google/callback`. If hostnames stay
`api.buscaoficio.co` / `app.buscaoficio.co`, **do not add a new URI**.

---

## 8. Migrations + smoke

- [ ] Alembic: SSH `docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head`
      **after** the image that contains the revision is running (or use the
      Vercel-era Actions job against `DATABASE_URL` if you kept it).
- [ ] Head as of 2026-09-07: `c8f3a91d4e20` (already applied on Supabase).
- [ ] OTP login, Google login, logout (`POST /api/auth/logout`), dashboard.
- [ ] `proxy.ts` must **never** 307 a `next-action` POST to `/login`.
- [ ] Promote a FastAdmin superuser (OTP signup + SQL) if the user table
      is empty on a new RDS.

---

## 9. Constraints that bit production before

- 913MB RAM — no on-box `docker build`.
- 8GB disk — prune after `up -d`.
- Pin pnpm via `packageManager` + Corepack in Dockerfiles; never
  `npm install -g pnpm` unpinned.
- Route Handlers behind Caddy must not trust `request.url` for redirects;
  use `FRONTEND_URL` (`app/api/auth/google/complete/route.ts`).
- PgBouncer: both statement caches off + unnamed prepares. Do not “fix”
  this with URL query flags.
- Never log tokens, passwords, or JWTs.

---

## 10. Context files on this branch

| File | Role |
| --- | --- |
| `Caddyfile` | **Required on EC2.** TLS + `app`/`api` reverse proxy. Deleted on `main`. |
| `.github/workflows/infra-manual-reminder.yml` | **Required on EC2.** Fails CI until compose/Caddy are copied to the box. Deleted on `main`. |
| `docs/deployment.md` | Compact EC2 deploy summary (pre-Vercel wording). |
| `memory-bank/activeContext.md` | Banner at top of this branch. |
| `memory-bank/techContext.md` / `systemPatterns.md` | OIDC, ECR, SSH rotation. |
| `.env.prod.example` | Compose/Caddy env template. |
| `.claude/agents/aws-deployer.md` | Local-only (gitignored); last verified 2026-08-23. Prefer this checklist + live AWS CLI. |
