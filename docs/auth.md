# Authentication

This document explains how authentication works in Buscaoficio, what flows are available, how users get access to protected resources, and what is not yet implemented.

---

## Overview

Authentication is handled by [fastapi-users](https://fastapi-users.github.io/fastapi-users/), a battle-tested library built on top of FastAPI. You do not need to read its full documentation to work on this project, but knowing it exists helps explain why the code is structured the way it is.

The project uses **JWT Bearer tokens**. After a user logs in they receive a token that must be included in every subsequent request as an `Authorization: Bearer <token>` header. Tokens expire after 1 hour (configurable via `ACCESS_TOKEN_EXPIRE_SECONDS`).

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
POST /auth/register               → creates the account
POST /auth/request-verify-token   → triggers the verification hook (see note below)
POST /auth/verify                 → marks the account as verified using the token
POST /auth/jwt/login              → returns a JWT
```

> **Why the verification step?** It confirms the user controls the email address they registered with. An unverified account can still log in — `is_verified` is informational unless you add a guard.

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

### 2 · Log in / log out

```
POST /auth/jwt/login    → email + password → JWT
POST /auth/jwt/logout   → invalidates the current token
```

The login endpoint expects `application/x-www-form-urlencoded` with `username` (the email) and `password`. This matches the OAuth2 convention used by the interactive docs at `/docs`.

---

### 3 · Password reset

For users who have forgotten their password. Requires that email is configured.

```
POST /auth/forgot-password   → sends a reset link to the email address
POST /auth/reset-password    → uses the token from the email to set a new password
```

After resetting, the user logs in normally via `POST /auth/jwt/login`.

> The API intentionally does not reveal whether the email exists in the database. Both valid and unknown emails receive the same empty response to avoid leaking user information.

---

## Permissions and authorization

The project currently provides **two levels of access**:

| Who | How it's enforced |
|-----|-------------------|
| Any authenticated active user | `current_active_user` dependency |
| Superusers only | `current_superuser` dependency |

These are injected as FastAPI dependencies in route handlers. For example, `/users/me` requires any active user, while `/users/{id}` (GET, PATCH, DELETE) requires a superuser.

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

There is no `createsuperuser` CLI command yet. The current workaround is to create a user via `POST /auth/register` and then promote it directly in the database:

```sql
UPDATE "user" SET is_superuser = true WHERE email = 'you@example.com';
```

Connect to the local database with:

```bash
docker compose exec db psql -U postgres -d postgres
```

> Adding a management command for this is a known gap and a good first contribution — see `commands/` for the pattern.

---

## Routes overview

All routes live under the `/auth` prefix and are defined in `fastapi_backend/app/routes/auth.py`.

> These routes were written explicitly (rather than using fastapi-users' built-in router) to allow clear docstrings and summary labels in the OpenAPI docs. The underlying logic still delegates to the `UserManager` from fastapi-users.

| Method | Path | Who can call it |
|--------|------|-----------------|
| POST | `/auth/register` | Anyone |
| POST | `/auth/jwt/login` | Anyone |
| POST | `/auth/jwt/logout` | Authenticated user |
| POST | `/auth/forgot-password` | Anyone |
| POST | `/auth/reset-password` | Anyone (needs the emailed token) |
| POST | `/auth/request-verify-token` | Anyone |
| POST | `/auth/verify` | Anyone (needs the emailed token) |

Interactive docs with a built-in "Authorize" button: **http://localhost:8001/docs**

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ACCESS_SECRET_KEY` | Signs JWT access tokens |
| `RESET_PASSWORD_SECRET_KEY` | Signs password-reset tokens |
| `VERIFICATION_SECRET_KEY` | Signs email-verification tokens |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | Token lifetime in seconds (default: 3600) |

Generate secrets locally with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## FAQ

**Q: Why are there explicit route handlers if fastapi-users already provides them?**  
A: To add meaningful `summary` labels and docstrings that appear in the OpenAPI docs. The logic inside still calls fastapi-users' `UserManager`.

**Q: I called `/auth/request-verify-token` but never received an email — is that normal?**  
A: Yes, for now. The verification email is not implemented yet. The token is printed to the server log instead. Copy it from there and post it to `POST /auth/verify` manually.

**Q: The `/auth/forgot-password` endpoint returned 202 but I never got an email — why?**  
A: Locally, emails are caught by MailHog at `http://localhost:8025`. Make sure the MailHog container is running (`make docker-up-mailhog`) and that your `.env` points to it. Note that password reset emails are sent; verification emails are not yet.

**Q: How do I know which token to use where?**  
A: There is only one token type — the JWT you get from `/auth/jwt/login`. Use it as `Authorization: Bearer <token>` on every protected request.

**Q: Can I create a superuser without touching the database directly?**  
A: Not yet. See the [Creating a superuser](#creating-a-superuser) section above.

**Q: Do I need to verify my email to log in?**  
A: No, `is_verified` is not checked at login. It is informational. You can add a check in `UserManager` or as a dependency if the product requires it.

**Q: Where do I add authorization logic for a new endpoint?**  
A: Add `Depends(current_active_user)` or `Depends(current_superuser)` as a parameter to your route handler. Both are exported from `app/users.py`.

**Q: What happens if I pass a wrong password several times?**  
A: There is no brute-force protection or account lockout at the application layer currently. This would need to be added (e.g., via rate limiting middleware or a Redis-backed attempt counter).
