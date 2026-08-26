# Backend - FastAPI (`fastapi_backend`)

Python API for Buscaoficio. Owns authentication, users, items, email, OpenAPI schema generation, and database migrations.

For the full-stack map and shared ports, see the [root README](../README.md).  
For the UI, see `[nextjs-frontend/README.md](../nextjs-frontend/README.md)`.

---

## Stack


| Piece                 | Choice                                          |
| --------------------- | ----------------------------------------------- |
| Framework             | FastAPI (async)                                 |
| Python                | 3.12                                            |
| Package manager       | **uv**                                          |
| Auth                  | **fastapi-users** (JWT bearer)                  |
| ORM                   | SQLAlchemy 2 + **asyncpg**                      |
| Migrations            | **Alembic** (async)                             |
| Validation / settings | Pydantic v2 + pydantic-settings                 |
| Pagination            | fastapi-pagination                              |
| Email                 | fastapi-mail + Jinja templates                  |
| Quality               | Ruff, mypy, pytest, pytest-asyncio              |
| Local SMTP catcher    | MailHog (via Compose)                           |
| Deploy                | AWS EC2 (Docker, `fastapi run app/main.py` — see [`docs/deployment.md`](../docs/deployment.md)) |


---



## What this service exposes



### Auth (`/auth`)

> For a full explanation of the auth flows, password rules, permissions model, and how to create a superuser, see **[docs/auth.md](../docs/auth.md)**.


| Method | Path                         | Purpose                    |
| ------ | ---------------------------- | -------------------------- |
| POST   | `/auth/register`             | Create user                |
| POST   | `/auth/jwt/login`            | Login → JWT                |
| POST   | `/auth/jwt/logout`           | Logout                     |
| POST   | `/auth/forgot-password`      | Start reset (sends email)  |
| POST   | `/auth/reset-password`       | Complete reset with token  |
| POST   | `/auth/request-verify-token` | Request verification email |
| POST   | `/auth/verify`               | Verify email with token    |




### Users (`/users`)

CRUD-style user management from fastapi-users (`UserRead` / `UserUpdate`).


| Method | Path          | Purpose                       |
| ------ | ------------- | ----------------------------- |
| GET    | `/users/me`   | Current authenticated user    |
| PATCH  | `/users/me`   | Update current user           |
| GET    | `/users/{id}` | Get user by id (superuser)    |
| PATCH  | `/users/{id}` | Update user by id (superuser) |
| DELETE | `/users/{id}` | Delete user by id (superuser) |




### Items (`/items`)


| Method | Path               | Purpose                        |
| ------ | ------------------ | ------------------------------ |
| GET    | `/items/`          | Paginated list (authenticated) |
| POST   | `/items/`          | Create item for current user   |
| DELETE | `/items/{item_id}` | Delete own item                |


Interactive docs locally: **[http://localhost:8001/docs](http://localhost:8001/docs)**

---



## Local ports


| What                       | Value                                                    |
| -------------------------- | -------------------------------------------------------- |
| API bind (this repo)       | **8001**                                                 |
| Swagger                    | [http://localhost:8001/docs](http://localhost:8001/docs) |
| App DB (host → container)  | **5434** → 5432                                          |
| Test DB (host → container) | **5435** → 5432                                          |
| MailHog SMTP               | 1025                                                     |
| MailHog UI                 | [http://localhost:8025](http://localhost:8025)           |


Inside Docker network the API still talks to Postgres as `db:5432` / `db_test:5432` (container ports). Host remaps only affect processes on your machine.

---



## Environment

Copy and edit:

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"  # run 3× for the secret keys
```



### Variables you must set


| Variable                    | Role                                                  |
| --------------------------- | ----------------------------------------------------- |
| `DATABASE_URL`              | App Postgres (`postgresql+asyncpg://…`)               |
| `TEST_DATABASE_URL`         | Test Postgres                                         |
| `ACCESS_SECRET_KEY`         | JWT access tokens                                     |
| `RESET_PASSWORD_SECRET_KEY` | Password reset tokens                                 |
| `VERIFICATION_SECRET_KEY`   | Email verification tokens                             |
| `CORS_ORIGINS`              | Allowed origins (JSON-like set, e.g. `["*"]` locally) |
| `FRONTEND_URL`              | Used in email links (default `http://localhost:3000`) |
| `OPENAPI_OUTPUT_FILE`       | Where schema is written                               |




### Local vs Docker Compose


| Mode                      | `DATABASE_URL` host                     | `OPENAPI_OUTPUT_FILE`                                  |
| ------------------------- | --------------------------------------- | ------------------------------------------------------ |
| API on host, DB in Docker | `localhost:5434`                        | `../nextjs-frontend/openapi.json` (see `.env.example`) |
| API in Compose            | `db:5432` (set in `docker-compose.yml`) | `./shared-data/openapi.json` → `local-shared-data/`    |


Mail settings in `.env.example` target MailHog (`MAIL_SERVER=localhost`, `MAIL_PORT=1025`, TLS off). Compose overrides `MAIL_SERVER=mailhog` for the backend container.

Optional: set `OPENAPI_URL=""` to hide `/docs` and `/openapi.json` (production hardening).

---



## How to run



### Preferred: Makefile (starts API **and** `watcher.py`)

From repo root:

```bash
# DB first
docker compose up -d db
make docker-migrate-db

# Optional email catcher
make docker-up-mailhog

# Install once
cd fastapi_backend && uv sync && cd ..

# Run
make start-backend
```

`start.sh` does two things:

1. `fastapi dev … --host 0.0.0.0 --port 8001 --reload`
2. `watcher.py` (mypy + OpenAPI schema regeneration)

**Do not** rely on only `uv run fastapi …` for day-to-day work - you will miss OpenAPI sync.

### Docker

```bash
make docker-build-backend
make docker-start-backend
```

Shell into the container: `make docker-backend-shell`.

---



## OpenAPI watcher (backend side)

`watcher.py` watches **only**:

- `app/main.py`
- `app/schemas.py`
- `app/routes/*.py`

On save it:

1. Runs **mypy**
2. Runs `python -m commands.generate_openapi_schema` → writes `OPENAPI_OUTPUT_FILE`

It does **not** watch `models.py`. Model-only edits reload the server (via `--reload`) but do **not** update OpenAPI or Postgres.

Manual schema export:

```bash
cd fastapi_backend && uv run python -m commands.generate_openapi_schema
# or
docker compose run --rm --no-deps -T backend uv run python -m commands.generate_openapi_schema
```

---



## Database & Alembic



### Models

- `User` - fastapi-users UUID table (email, hashed password, flags)
- `Item` - `name`, `description`, `quantity`, FK → `user` (cascade delete)



### Rules (explicit)

1. Editing `models.py` does **not** change Postgres by itself.
2. Alembic is the source of truth for schema.
3. `create_db_and_tables()` exists in code but is **not** the supported workflow - use migrations.
4. Alembic uses `DATABASE_URL`, not `TEST_DATABASE_URL`.



### Create + apply a migration

```bash
# After changing models
make docker-db-schema migration_name="add_column_x"

# Review the file under alembic_migrations/versions/
make docker-migrate-db
```



### ⚠️ Migration safety: review before applying, every time

**DO:**

- Always **open and read** the generated file under `alembic_migrations/versions/` before running `make docker-migrate-db`. Never chain schema-generate → apply without a review step in between.
- When a migration touches a rename (table or column), check the generated `upgrade()` for a `drop_table`/`create_table` (or `drop_column`/`add_column`) pair that represents the *same* logical entity, and rewrite it by hand as `op.rename_table(...)` / `op.alter_column(..., new_column_name=...)`.
- Before trusting any rename as safe, check whether the table already has rows: `SELECT count(*) FROM <table>;`. "It's just dev data" has already been wrong once on this project.

**DON'T:**

- Don't assume renaming a model in `models.py` (e.g. changing `__tablename__`) gets captured as a rename by `alembic revision --autogenerate`. **Alembic autogenerate has no concept of "rename."** It diffs models against the live DB schema by name only, so a rename always comes out as `drop_table(old)` + `create_table(new)`. Applied as-is, this **permanently deletes every row in the old table** — data loss, not a schema change.
- Don't run `make docker-migrate-db` immediately after `make docker-db-schema` out of habit, even mid-debugging. The apply step is irreversible against real data; the review step costs nothing.

**Why this is here:** renaming `user` → `usuarios` in this project autogenerated exactly that destructive drop+create. Applied blindly, it would have deleted the table's one existing row — which turned out to be the project's only superuser account. It was caught only because the migration file was reviewed before `make docker-migrate-db` ran. Foreign keys don't need special handling in a rename — Postgres tracks them by OID, not by table name, so they survive automatically once the table itself is properly renamed.

Existing baseline revisions:

- `402d067a8b92` - user table
- `b389592974f8` - item model



### Tests DB

```bash
make docker-up-test-db
make test-backend
# or
make docker-test-backend
```

Tests use `TEST_DATABASE_URL` and recreate schema in `tests/conftest.py`.

### Connection pooling

The engine uses `NullPool` so connection behavior is uniform across dev and prod (no sticky pool).

---



## Email (local)

```bash
make docker-up-mailhog
```

- SMTP: `localhost:1025`
- UI: [http://localhost:8025](http://localhost:8025)

Password recovery emails land in MailHog instead of real inboxes.  
MailHog is unmaintained upstream; **Mailpit** is a common drop-in replacement later if you want.

Production: configure real SMTP (or a provider) via `MAIL_*` env vars - do not use MailHog in prod.

---



## Auth behavior notes

- Transport: **Bearer JWT** (`Authorization: Bearer <token>`).
- Login endpoint for OpenAPI/client: `/auth/jwt/login`.
- Password policy is enforced in `UserManager` (`app/users.py`).
- Reset / verification emails use secrets from env; links use `FRONTEND_URL`.
- After register, `on_after_register` currently logs; extend here for welcome emails if needed.

---



## Deploy - backend perspective

Production is AWS (EC2 + Docker + Caddy), not Vercel. The container runs `fastapi run app/main.py --workers 2`. RDS enforces SSL; asyncpg uses `ssl="prefer"` in `app/database.py` and Alembic, so no URL flag is needed.

### Required production env

- `DATABASE_URL` (RDS endpoint, TLS enforced)
- `ACCESS_SECRET_KEY`, `RESET_PASSWORD_SECRET_KEY`, `VERIFICATION_SECRET_KEY` (strong secrets)
- `CORS_ORIGINS` - start broad only temporarily; then set to the real frontend origin(s)
- `FRONTEND_URL` - production frontend URL (for email links)
- Mail provider settings for real delivery



### Checklist

1. Create the app database on RDS (see `docs/deployment.md` first-time setup) and set `DATABASE_URL` + all `*_SECRET_KEY`s.
2. CI builds the image and the box pulls it via `docker-compose.prod.yml` — nothing to do by hand.
3. Run migrations manually against RDS: `docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head` (reviewed before applying, by project convention).
4. After frontend URL is known, tighten `CORS_ORIGINS` to the real origin(s).

---



## Useful paths

```
fastapi_backend/
├── app/
│   ├── main.py          # App + routers
│   ├── users.py         # Auth backend + UserManager
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── routes/items.py  # Items API
│   ├── database.py      # Engine + sessions
│   ├── email.py         # Mail helpers
│   └── config.py        # Settings
├── alembic_migrations/
├── commands/generate_openapi_schema.py
├── start.sh             # Dev: API + watcher
├── watcher.py
└── tests/
```

---



## Commands quick reference


| Task                | Command                                             |
| ------------------- | --------------------------------------------------- |
| Start API + watcher | `make start-backend`                                |
| Start API (Docker)  | `make docker-start-backend`                         |
| Migrate             | `make docker-migrate-db`                            |
| New migration       | `make docker-db-schema migration_name="…"`          |
| Tests               | `make test-backend` / `make docker-test-backend`    |
| MailHog             | `make docker-up-mailhog`                            |
| Export OpenAPI      | `uv run python -m commands.generate_openapi_schema` |
| Shell               | `make docker-backend-shell`                         |


