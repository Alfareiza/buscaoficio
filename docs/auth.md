# Authentication

This document explains how authentication works in Buscaoficio, what flows are available, how users get access to protected resources, and what is not yet implemented.

---

## Overview

Authentication is handled by [fastapi-users](https://fastapi-users.github.io/fastapi-users/), a battle-tested library built on top of FastAPI. You do not need to read its full documentation to work on this project, but knowing it exists helps explain why the code is structured the way it is.

The project uses **JWT Bearer access tokens paired with rotating refresh tokens**. After a user logs in they receive a short-lived access token (used as `Authorization: Bearer <token>` on every subsequent request) plus a long-lived refresh token set as an HttpOnly cookie. See [Refresh tokens & rotation](#refresh-tokens--rotation) below for the full flow.

Passwords are hashed with **Argon2** (the recommended modern algorithm). bcrypt is registered as a fallback so that passwords hashed with older tools can still be verified.

---

## User model

Each user has:

| Field | Notes |
|-------|-------|
| `id` | UUID, auto-generated |
| `email` | unique, used as the login identifier |
| `hashed_password` | never stored in plain text |
| `is_active` | must be `true` to log in |
| `is_superuser` | grants admin-level access |
| `is_verified` | set to `true` after email verification |

---

## Password rules

When registering or resetting a password the following rules are enforced:

- At least 8 characters
- Must not contain the user's email address
- At least one uppercase letter
- At least one special character (`!@#$%^&*(),.?":{}|<>`)

---

## Available flows

### 1 · Register → verify → log in (happy path)

This is the normal path for a new user.

```
POST /api/v1/auth/register               → creates the account
POST /api/v1/auth/request-verify-token   → triggers the verification hook (see note below)
POST /api/v1/auth/verify                 → marks the account as verified using the token
POST /api/v1/auth/jwt/login              → returns a JWT
```

> **Why the verification step?** It confirms the user controls the email address they registered with. An unverified account can still log in — `is_verified` is informational unless you add a guard.

#### Registering as cliente or profesional

Buscaoficio users register with one of two roles (a user can hold both).
Each role's registration is a single request that creates the `usuarios`
row and the role's `clientes`/`profesionales` row together — no separate
call to `POST /auth/register` first.

```
POST /api/v1/auth/register/cliente       → creates the account + cliente profile
POST /api/v1/auth/register/profesional   → creates the account + profesional profile
```

Each accepts the same fields as `POST /api/v1/auth/register` (`email`,
`password`, `nombre_completo`, optional `whatsapp`) plus the role's own
fields (`direccion_default`/`referido_por_id` for cliente;
`documento_tipo`/`documento_numero`/`anos_experiencia`/`foto_perfil_url`
for profesional). Both return `UserRead` and follow with the same
verify → log in steps above.

> **Known gap:** there is currently no REST endpoint to add the *second*
> role to an account that already registered with one — `/api/v1/users/me/cliente`
> and `/api/v1/users/me/profesional` are GET/PATCH/DELETE only now (the POST
> variants were removed when registration consolidated into the two
> endpoints above). An admin can still attach the second role via the
> FastAdmin panel (`/admin`). If self-service dual-role upgrade is needed,
> a `POST /api/v1/users/me/cliente` (or `/profesional`)-style endpoint
> would need to be reintroduced.

#### How the verification token reaches the user

**This is not fully implemented yet.** When `POST /auth/request-verify-token` is called, fastapi-users generates a signed token and calls the `on_after_request_verify` hook in `UserManager`. Right now that hook only prints the token to the server log:

```python
# app/users.py
async def on_after_request_verify(self, user, token, request=None):
    print(f"Verification requested for user {user.id}. Verification token: {token}")
```

No email is sent for verification. To complete the flow during development you can copy the token from the server output and post it manually to `POST /auth/verify`.

Compare this with password reset, which **is** fully wired up: `on_after_forgot_password` calls `send_reset_password_email`, which sends an HTML email containing a link to `{FRONTEND_URL}/password-recovery/confirm?token=<token>`. The frontend page reads that query parameter and posts it to `POST /auth/reset-password` on behalf of the user.

The verification flow needs the same treatment: implement `send_verification_email` in `app/email.py` and call it from `on_after_request_verify`. The frontend would then need a `/verify?token=<token>` page that posts to `POST /auth/verify`.

---

### 2 · Log in / refresh / log out

```
POST /api/v1/auth/jwt/login     → email + password → access token + refresh cookies
POST /api/v1/auth/jwt/refresh   → rotates the refresh token, returns a new access token
POST /api/v1/auth/jwt/logout    → revokes all refresh tokens for the user
```

The login endpoint expects `application/x-www-form-urlencoded` with `username` (the email) and `password`. This matches the OAuth2 convention used by the interactive docs at `/docs`.

---

## Refresh tokens & rotation

Buscaoficio uses **rotating refresh tokens with database-backed revocation and a double-submit fingerprint cookie**. This is the standard pattern for JWT auth in browser apps: short-lived access tokens limit the blast radius of a stolen token, while refresh tokens let the session persist without forcing frequent re-logins.

### Token lifetimes

| Token | Lifetime | Storage |
|-------|----------|---------|
| Access token | 15 minutes (`ACCESS_TOKEN_EXPIRE_SECONDS`) | Returned in the login/refresh response body; sent as `Authorization: Bearer <token>` |
| Refresh token | 30 days (`REFRESH_TOKEN_EXPIRE_SECONDS`) | HttpOnly/Secure/SameSite=Strict cookie, scoped to `/api/v1/auth/jwt/refresh`; hash stored in `refresh_tokens` table |
| Fingerprint token | Same as refresh token | HttpOnly/Secure/SameSite=Strict cookie, scoped to `/api/v1/auth/jwt/refresh`; hash stored alongside the refresh token row |

### How it works

1. **Login** (`POST /auth/jwt/login`) generates:
   - A JWT access token (returned in the response body)
   - A random refresh token + a random fingerprint token (both set as HttpOnly cookies, path-scoped to `/api/v1/auth/jwt/refresh` so they are never sent to other endpoints)
   - Both raw tokens are hashed (SHA-256) and the hashes are stored in the `refresh_tokens` table, tied to the user and the request's IP

2. **Refresh** (`POST /auth/jwt/refresh`) is called by the frontend shortly before the access token expires:
   - The server hashes the incoming `refreshToken` and `fingerprintToken` cookies and looks up a matching, non-revoked, non-expired row
   - If valid: the old row is revoked, a new refresh/fingerprint pair is generated and stored (**rotation**), and a new access token is returned
   - If the refresh token hash matches a row that **already has a newer generation** (i.e. someone is replaying an old, already-rotated token): every active refresh token for that user is revoked and the request is rejected with 401. This is the **theft-detection** trigger — legitimate clients always use the newest token, so a replay is a strong signal of a stolen token.

3. **Logout** (`POST /auth/jwt/logout`) revokes **all** refresh tokens for the user (not just the current one), so logging out on one device ends every session for that account. The refresh/fingerprint cookies are also cleared.

### Why a separate fingerprint cookie?

The fingerprint token implements a **double-submit cookie pattern**: even if a refresh token leaks (e.g. via a logging bug or an XSS payload that can read response bodies), it is useless without the paired fingerprint cookie, which — being HttpOnly — is never exposed to JavaScript. Both values are required on every `/refresh` call and both are hashed independently in the database.

### Database model

`RefreshToken` (`fastapi_backend/app/models.py`) — table `refresh_tokens`:

| Column | Notes |
|--------|-------|
| `user_id` | FK to `usuarios.id` |
| `refresh_token_hash` | SHA-256 hash of the raw refresh token cookie |
| `fingerprint_hash` | SHA-256 hash of the raw fingerprint token cookie |
| `expires_at` | Set at issuance to `now() + REFRESH_TOKEN_EXPIRE_SECONDS` |
| `revoked_at` | `NULL` while active; set on rotation, logout, or theft detection |
| `created_ip` | IP the token was issued to (from `X-Forwarded-For` or the connecting socket) |

All rotation/validation/revocation logic lives in `RefreshTokenManager` (`fastapi_backend/app/refresh_token_manager.py`).

### What is NOT implemented yet

- The frontend does not yet call `/auth/jwt/refresh` automatically before the access token expires (silent refresh) or synchronize logout across browser tabs — this is tracked separately from the backend work.
- Expired/revoked rows are not purged; there is no cleanup job for the `refresh_tokens` table yet.

---

### 3 · Password reset

For users who have forgotten their password. Requires that email is configured.

```
POST /api/v1/auth/forgot-password   → sends a reset link to the email address
POST /api/v1/auth/reset-password    → uses the token from the email to set a new password
```

After resetting, the user logs in normally via `POST /api/v1/auth/jwt/login`.

> The API intentionally does not reveal whether the email exists in the database. Both valid and unknown emails receive the same empty response to avoid leaking user information.

---

## Permissions and authorization

The project currently provides **two levels of access**:

| Who | How it's enforced |
|-----|-------------------|
| Any authenticated active user | `current_active_user` dependency |
| Superusers only | `current_superuser` dependency |

These are injected as FastAPI dependencies in route handlers. For example, `/api/v1/users/me` requires any active user, while `/api/v1/users/{id}` (GET, PATCH, DELETE) requires a superuser.

**What is NOT implemented yet:**

- Role-based access control (RBAC) — there is no concept of roles beyond the binary `is_superuser` flag.
- Resource-level ownership checks beyond the items endpoints — items are scoped to the authenticated user, but there is no general ownership framework.
- Fine-grained permissions per endpoint or per object.

If you need to protect a route, pick the appropriate dependency from `app/users.py`:

```python
from app.users import current_active_user, current_superuser

# Any logged-in user
@router.get("/something")
async def my_route(user: User = Depends(current_active_user)):
    ...

# Superusers only
@router.get("/admin/something")
async def admin_route(user: User = Depends(current_superuser)):
    ...
```

---

## Creating a superuser

There is no `createsuperuser` CLI command yet. The current workaround is to create a user via `POST /api/v1/auth/register` and then promote it directly in the database:

```sql
UPDATE usuarios SET is_superuser = true WHERE email = 'you@example.com';
```

Connect to the local database with:

```bash
docker compose exec db psql -U postgres -d postgres
```

> Adding a management command for this is a known gap and a good first contribution — see `commands/` for the pattern.

---

## Routes overview

All routes live under the `/api/v1/auth` prefix and are defined in `fastapi_backend/app/routes/auth.py`.

> These routes were written explicitly (rather than using fastapi-users' built-in router) to allow clear docstrings and summary labels in the OpenAPI docs. The underlying logic still delegates to the `UserManager` from fastapi-users.

| Method | Path | Who can call it |
|--------|------|-----------------|
| POST | `/api/v1/auth/register` | Anyone |
| POST | `/api/v1/auth/register/cliente` | Anyone |
| POST | `/api/v1/auth/register/profesional` | Anyone |
| POST | `/api/v1/auth/jwt/login` | Anyone |
| POST | `/api/v1/auth/jwt/refresh` | Anyone with a valid refresh + fingerprint cookie pair |
| POST | `/api/v1/auth/jwt/logout` | Authenticated user |
| POST | `/api/v1/auth/forgot-password` | Anyone |
| POST | `/api/v1/auth/reset-password` | Anyone (needs the emailed token) |
| POST | `/api/v1/auth/request-verify-token` | Anyone |
| POST | `/api/v1/auth/verify` | Anyone (needs the emailed token) |

Interactive docs with a built-in "Authorize" button: **http://localhost:8001/docs**

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ACCESS_SECRET_KEY` | Signs JWT access tokens |
| `RESET_PASSWORD_SECRET_KEY` | Signs password-reset tokens |
| `VERIFICATION_SECRET_KEY` | Signs email-verification tokens |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | Access token lifetime in seconds (default: 900 = 15 minutes) |
| `REFRESH_TOKEN_EXPIRE_SECONDS` | Refresh token lifetime in seconds (default: 2592000 = 30 days) |

Generate secrets locally with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## FAQ

**Q: Why are there explicit route handlers if fastapi-users already provides them?**  
A: To add meaningful `summary` labels and docstrings that appear in the OpenAPI docs. The logic inside still calls fastapi-users' `UserManager`.

**Q: I called `/api/v1/auth/request-verify-token` but never received an email — is that normal?**  
A: Yes, for now. The verification email is not implemented yet. The token is printed to the server log instead. Copy it from there and post it to `POST /api/v1/auth/verify` manually.

**Q: The `/api/v1/auth/forgot-password` endpoint returned 202 but I never got an email — why?**  
A: Locally, emails are caught by MailHog at `http://localhost:8025`. Make sure the MailHog container is running (`make docker-up-mailhog`) and that your `.env` points to it. Note that password reset emails are sent; verification emails are not yet.

**Q: How do I know which token to use where?**  
A: The access token from `/api/v1/auth/jwt/login` (or `/api/v1/auth/jwt/refresh`) is used as `Authorization: Bearer <token>` on every protected request. The refresh and fingerprint tokens are cookies — you never read or send them manually; the browser attaches them automatically on calls to `/api/v1/auth/jwt/refresh` because they're scoped to that path.

**Q: My access token expired — what do I do?**  
A: Call `POST /api/v1/auth/jwt/refresh` (no body needed; it reads the refresh/fingerprint cookies automatically) to get a new access token. If that also returns 401, the refresh token has expired, been revoked, or reuse was detected — the user needs to log in again.

**Q: What happens if a refresh token is used twice (e.g. replayed after rotation)?**  
A: All refresh tokens for that user are immediately revoked and the request is rejected with 401. This is a deliberate theft-detection measure — see [Refresh tokens & rotation](#refresh-tokens--rotation).

**Q: How does the app know when the access token is about to expire, so it can refresh it before that happens?**  
A: This is a fair thing to wonder, because there's no alarm clock sitting on the server counting down. The trick is that a JWT already carries its own expiry time inside it — the `exp` field, buried in the token itself. It's not secret or encrypted, just signed, so anyone holding the token (including the browser) can peek at it. So the plan is: when the frontend gets a fresh access token, it opens it up, reads that `exp` timestamp, and sets a timer to quietly ask for a new one a couple of minutes before that moment arrives — well before the user would ever notice anything expired. One thing worth flagging: the login/refresh responses also include a field called `expires_in` that's *supposed* to make this easier by just telling you the lifetime directly, but right now it's returning the wrong number (it reports the refresh token's 30-day lifetime instead of the access token's real 15-minute one). So for now, reading the `exp` field inside the token itself is the reliable way — that part is tracked as frontend work still to be built.

**Q: What happens if I just close the browser tab instead of clicking "log out"?**  
A: Nothing dramatic happens right away, and that's by design. The session doesn't end the instant you close the tab — the refresh token cookie is still sitting there, valid, ready to pick up where you left off if you reopen the site (this is exactly why "remember me for a while" sessions feel seamless). It'll naturally stop working after 30 days of not being used, or sooner if you log out from somewhere, or if something looks like it might've been stolen. So: closing the tab is safe and normal, it just isn't the same thing as logging out — logging out is the only thing that immediately kills the session everywhere.

**Q: Can I create a superuser without touching the database directly?**  
A: Not yet. See the [Creating a superuser](#creating-a-superuser) section above.

**Q: Do I need to verify my email to log in?**  
A: No, `is_verified` is not checked at login. It is informational. You can add a check in `UserManager` or as a dependency if the product requires it.

**Q: Where do I add authorization logic for a new endpoint?**  
A: Add `Depends(current_active_user)` or `Depends(current_superuser)` as a parameter to your route handler. Both are exported from `app/users.py`.

**Q: What happens if I pass a wrong password several times?**  
A: There is no brute-force protection or account lockout at the application layer currently. This would need to be added (e.g., via rate limiting middleware or a Redis-backed attempt counter).
