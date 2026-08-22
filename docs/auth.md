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

### 0 · Passwordless login (primary flow, since 2026-08-18)

The frontend's `/login` page uses **email OTP**, not password + register forms. Login and signup are the same screen — the backend doesn't know which the user "meant" until the OTP is verified.

```
POST /api/v1/auth/otp/request              → {email} → sends a 6-digit code, always 202
POST /api/v1/auth/otp/verify               → {email, code} → branches:
  · email already has an account  → logs in (access token + refresh/fingerprint
                                      cookies), {status: "existing_user", has_role}
  · email is new                  → {status: "new_user", registration_token}

# only reached for a "new_user" response above:
POST /api/v1/auth/register/cliente/otp     → {registration_token, nombre_completo, ...} → creates account + logs in
POST /api/v1/auth/register/profesional/otp → {registration_token, nombre_completo, documento_tipo, documento_numero, ...} → creates account + logs in
```

Design notes:
- **No account is created by `/otp/request` or `/otp/verify`.** A brand-new email only gets a short-lived signed `registration_token` (proves OTP ownership, ~15 min, see `OtpManager.issue_registration_token`) — the `usuarios` row is created later, atomically with its `clientes`/`profesionales` row, in the `/register/*/otp` call. This means an abandoned signup (user closes the tab after seeing the code) never leaves a ghost account.
- **Role selection is mandatory**, unlike a generic passwordless flow — `Cliente` needs no extra fields, but `Profesional` requires `documento_tipo`/`documento_numero` (real ID document data), so the frontend's role-choice step collects those two fields inline before calling `/register/profesional/otp`.
- OTP-created accounts get a **random, never-disclosed password** (`secrets.token_urlsafe(32)`, hashed the normal way) purely to satisfy the underlying fastapi-users schema (`hashed_password` is `NOT NULL`) — it can never actually be used, since nobody (including the user) knows it. `is_verified` is set `true` immediately, since receiving and entering the code already proves mailbox ownership — the separate `request-verify-token`/`verify` flow below is redundant for these accounts.
- Session issuance (access token + refresh/fingerprint cookies) is shared code — `build_session_response()` in `app/refresh_token_manager.py` — used by OTP verify (existing user) and both OTP-backed registration routes, so the cookie-setting logic exists in exactly one place.
- Codes: 6 digits, 10-minute expiry (`OTP_CODE_EXPIRE_SECONDS`), max 5 verify attempts, 60s resend cooldown. Storage/validation lives in `OtpManager` (`app/otp_manager.py`), modeled on `RefreshTokenManager` — codes are hashed (SHA-256), never stored raw, in the `email_otps` table.
- **What is NOT implemented:** real rate-limiting infra (only the basic cooldown/attempt-cap above — no IP-level throttling or CAPTCHA), and cleanup of expired `email_otps` rows (same known gap as `refresh_tokens`).
- **Known gap:** there is currently no REST endpoint to add the *second* role to an account that already registered with one — `/api/v1/users/me/cliente` and `/api/v1/users/me/profesional` are GET/PATCH/DELETE only (there's no POST). An admin can still attach the second role via the FastAdmin panel (`/admin`). If self-service dual-role upgrade is needed, a `POST /api/v1/users/me/cliente` (or `/profesional`)-style endpoint would need to be added.
- **Password-based login and registration were removed** (`/jwt/login`, `/register`, `/register/cliente`, `/register/profesional` — this was the frontend's only client, and nothing else called them; see git history around 2026-08-18 for the removal). `/forgot-password`/`/reset-password` and `/request-verify-token`/`/verify` still exist in the code but are now vestigial: there is no password-login route left to sign in with a reset password, and OTP-created accounts are already `is_verified=true` at creation, so nothing in the current flow ever produces an account these routes need to act on. See `nextjs-frontend`'s `/password-recovery` pages for the same "kept but unlinked" state on the frontend side.

### 0b · Google Sign-In

An alternative to email OTP for proving an email, using Google's OAuth 2.0 **authorization code flow** (server-side redirect — no Google JS ever runs in the browser, consistent with this app being server-mediated). It reaches the exact same fork as OTP verification (existing account → log in; new email → mandatory onboarding, including role selection) rather than being a separate parallel signup path — **role selection (cliente/profesional) and WhatsApp are still required after a Google signup**, Google only supplies a verified email and a name.

```
GET  /api/v1/auth/google/authorize   → 302 redirect to Google's consent screen
GET  /api/v1/auth/google/callback    → Google redirects here with ?code&state; this route
                                         never sets cookies itself — see note below — it always
                                         redirects onward to the frontend:
  · new email        → {FRONTEND_URL}/register?registration_token=...&provider=google&name=...
  · existing account  → {FRONTEND_URL}/api/auth/google/complete?google_session_token=...
  · any failure       → {FRONTEND_URL}/login?error=google_auth_failed
POST /api/v1/auth/google/session     → {google_session_token} → logs in (access token +
                                         refresh/fingerprint cookies), same shape as /otp/verify's
                                         existing_user response
```

Design notes:
- **Why a `google_session_token` round trip instead of setting cookies directly in the callback:** `/google/callback` is hit by the *browser itself* (a top-level navigation Google initiates), not by a Next.js Server Action. But every cookie in this app is set by the **Next.js server on its own origin** (`app.buscaoficio.co`) — see [Frontend: cookie forwarding & silent refresh](#frontend-cookie-forwarding--silent-refresh) — never by FastAPI directly on the browser. If the FastAPI callback set cookies on its own redirect response, they'd land on the wrong origin (`api.buscaoficio.co`) and nothing in the app reads cookies from there. So the callback instead issues a short-lived (2 min), single-purpose `google_session_token` and redirects to it.
- **The session cookies are `SameSite=Lax`, not `Strict`, and that is load-bearing** (`lib/auth-cookies.ts`). Google returns the browser through a redirect chain that *starts* on `accounts.google.com`; browsers judge SameSite by the chain's initiator, so `Strict` cookies — even though set correctly by the Route Handler — are withheld from the final navigation to `/dashboard`. `proxy.ts` then sees no `accessToken` and redirects to `/login`, where the user clicks Google again: an endless login loop. This only affects the Google flow; the OTP flow is entirely same-site, which is why it never showed the symptom. `Lax` still withholds cookies from cross-site POSTs (the CSRF case that matters), and `/jwt/refresh` additionally requires the paired fingerprint cookie.
- **Why a Route Handler, not a page** (`nextjs-frontend/app/api/auth/google/complete/route.ts`): the token exchange has to happen *before anything renders*, or the user sees a spinner/blank card flash between Google and the dashboard. A Route Handler runs entirely server-side — it POSTs the token to `/auth/google/session`, sets the session cookies on its own redirect response, and 307s straight to `/dashboard`. The browser's navigation is Google → backend callback → this handler → `/dashboard`, with exactly two document requests and no intermediate screen. A page would have to mount, run an effect, then navigate — which is precisely the visible in-between state this avoids.
- **The "Continuar como {name}" card** on `/login`: after any Google login or Google-backed registration, a `lastGoogleIdentity` cookie (`lib/google-identity-cookie.ts`) stores the user's name, email and Google photo URL. `/login`'s Server Component reads it during render, so the card is in the first HTML — no client effect, no flash of the blank form. It's a **cookie rather than localStorage** for exactly that reason (a Server Component can't read localStorage), and it deliberately **outlives logout**: a returning user should see their own name whether their session expired or they signed out on purpose. It holds no credential — clicking the card still runs the full OAuth flow — and is never trusted server-side for authorization. Only the first name is shown, matching Google's own "Continue as X"; the full name would overflow the card.
- **New emails reuse the OTP registration_token machinery.** `/google/callback` calls the same `OtpManager.issue_registration_token()` used by `/otp/verify`, just with two extra optional claims (`google_sub`, `nombre_completo`) threaded through. This means `POST /register/{cliente,profesional}/otp` needed no new routes — it already just needs a valid `registration_token`, and now persists `google_sub` onto the new `User` row if the token carries one.
- **Account linking is by verified email**, matching how this app already treats email as the canonical identity. If a `usuarios` row already exists for the Google account's email (e.g. it was created via OTP), a Google login logs into that same account and backfills its `google_sub` column on first use — it does not create a second account.
- **Google identity is a single column, not a separate table**: `usuarios.google_sub` (nullable, unique). Only Google is supported today; a second provider would justify moving to a proper multi-provider `oauth_accounts` table, but that's speculative for now.
- The Google `id_token` (a signed JWT returned alongside the access token when the `openid` scope is requested) is verified against Google's published JWKS (`GoogleOAuthManager`, `app/google_oauth_manager.py`) rather than calling Google's People API — one HTTP round trip instead of two, and it's the standard OIDC pattern. An unverified email (`email_verified: false` in the token) is rejected outright.
- The `state` parameter (CSRF protection between `/authorize` and `/callback`) is a signed, short-lived JWT rather than a server-side session lookup — this is a stateless API with no session store.
- **Not implemented**: linking a *second* OAuth provider to an account, or self-service unlinking of `google_sub`.

---

### 1 · Log in / refresh / log out

```
POST /api/v1/auth/jwt/refresh   → rotates the refresh token, returns a new access token
POST /api/v1/auth/jwt/logout    → revokes all refresh tokens for the user
```

There is no password-based login route — sessions are created by `POST /api/v1/auth/otp/verify` (section 0 above) or by the OTP-backed registration routes, both of which call the same `build_session_response()` that used to back `/jwt/login`. `/jwt/refresh` and `/jwt/logout` are unchanged by which route created the session.

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

1. **Login** (`POST /auth/otp/verify`, existing user — see [Passwordless login](#0--passwordless-login-primary-flow-since-2026-08-18)) generates, via `build_session_response()`:
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

- Expired/revoked rows are not purged; there is no cleanup job for the `refresh_tokens` table yet.

---

## Frontend: cookie forwarding & silent refresh

**This app is Server Actions + Edge middleware based, not a client-side SPA.** `API_BASE_URL` (no `NEXT_PUBLIC_` prefix) means the browser never calls FastAPI directly — every request goes through a Next.js Server Action (`components/actions/*.ts`) or `proxy.ts` (Edge middleware, matches `/dashboard/:path*`), both of which do a **server-to-server** fetch to the backend. This matters a lot for how refresh tokens work here, and is easy to get wrong by copying a typical SPA pattern.

### The cookie-forwarding problem

When a Server Action calls the backend (e.g. `otp-auth-action.ts` calling `authOtpVerify()`), that request is made by the **Next.js server**, not the browser. FastAPI's `Set-Cookie` response headers for `refreshToken`/`fingerprintToken` land on that server-to-server response — they do not reach the browser automatically the way they would on a direct browser→backend call. The Next.js server has to explicitly re-set them on its own response for the browser to ever see them.

`lib/auth-cookies.ts` provides the shared helpers:
- `forwardAuthCookies(setCookieHeaders, cookieWriter)` — parses the raw `Set-Cookie` strings from a backend response (`response.headers["set-cookie"]` on the axios-based generated client) and re-applies each as a cookie on the Next.js response, with `httpOnly: true`, `sameSite: "strict"`, `path: "/"`, and `secure` gated on `NODE_ENV === "production"` (hardcoding `secure: true` would silently break these cookies in local dev over `http://localhost:3000` — the same class of issue as the `https://` fix needed in the backend's own test client).
- `setAccessTokenCookie` / `clearAuthCookies` — the same treatment for the access token cookie and for clearing all three on logout or a dead session.
- `decodeJwtExpiryMs` — reads the access token's `exp` claim client-side-safe (no signature verification needed; it's only used to decide *when* to refresh, never to authorize anything).

These helpers accept a small structural `CookieWriter` interface (`set`/`delete`) rather than importing a concrete cookie type, since they're used from two different runtimes with different but compatible cookie APIs: `next/headers`'s `cookies()` in Server Actions, and `NextResponse.cookies` in middleware.

### Silent refresh via `proxy.ts`

There is no persistent client-side JS holding a refresh timer — instead, `proxy.ts` (which already runs on every `/dashboard/:path*` request, including Server Action POSTs to those routes) decodes the access token's `exp` before validating it. If it's expired or within 2 minutes of expiring, the middleware:
1. Reads `refreshToken` + `fingerprintToken` from the incoming request's cookies
2. Calls `POST {API_BASE_URL}/api/v1/auth/jwt/refresh` via a plain `fetch()` (not the axios-based generated client — native `fetch` is simpler to guarantee Edge-runtime-compatible), manually forwarding the cookies as a `Cookie` request header, since server-to-server calls don't auto-attach the browser's cookies
3. On success: forwards the new cookies via `forwardAuthCookies` onto the outgoing `NextResponse`, and continues the request with the new access token
4. On failure (refresh token invalid, expired, or revoked — including theft-detection revocation): clears all three cookies and redirects to `/login`

If the access token is missing `refreshToken`/`fingerprintToken` cookies at all when a refresh is needed, that's treated as a dead session (redirect to `/login`) rather than attempted.

### Reactive fallback in Server Actions

Middleware covers the common case (page loads and same-route Server Action POSTs), but as a narrower safety net, `items-action.ts` checks each backend call's result with `isUnauthorizedError()` (`lib/api-errors.ts`) — if a call still comes back 401 (e.g. a token revoked between the middleware's check and the actual backend call), the action clears cookies and redirects to `/login` instead of surfacing a generic error.

### How page protection actually works — and how to add a new protected page

There is exactly **one** gate, and it is not per-page code. `proxy.ts` only runs on routes matching its `config.matcher`:

```ts
export const config = {
  matcher: ["/dashboard/:path*"],
};
```

Any route matching that pattern gets the full treatment before it renders: no `accessToken` cookie → redirect to `/login`; token expired or near-expiry → silent refresh (see above) or redirect if that fails; token present but rejected by the backend → redirect. Any route that does **not** match — `/`, `/login`, `/register`, `/password-recovery`, or any brand-new top-level page you add — gets **none of this**. There is no auth check inside `app/dashboard/layout.tsx` or any other layout; the layout is UI chrome only. The middleware's `matcher` is the entire mechanism.

**If a new page needs a logged-in user:**
- Put it under `/dashboard/...` (e.g. `app/dashboard/requests/page.tsx`) — it's covered automatically, no changes needed anywhere else.
- If it must live outside `/dashboard` for routing reasons, add its path to the `matcher` array in `proxy.ts`, e.g. `["/dashboard/:path*", "/requests/:path*"]`.

**If a new page must stay public**, no action is needed — just don't put it under `/dashboard` and don't add it to `matcher`.

This also means Server Action POSTs are only protected when their route matches the same pattern — a Server Action file itself has no way to opt in or out of middleware coverage on its own; it inherits whatever protection the page/route it's called from has. The narrower, request-level backstop for a call that slips through (e.g. a token revoked mid-request) is the reactive `isUnauthorizedError()` check described above, not the middleware.

### Cross-tab logout — no active sync needed

Unlike a typical SPA storing tokens in `localStorage` or in-memory state, these are cookies — the browser already shares them across every tab for the same origin. There's no separate client-side session state that can go stale independently per tab. The only gap is a tab with already-rendered "logged in" UI not knowing a session ended until its next navigation or action — which is exactly when `proxy.ts` (or the Server Action fallback above) would catch it and redirect. No `BroadcastChannel` or `storage`-event based sync is implemented, since it would be solving a problem this cookie-based architecture doesn't actually have.

---

### 2 · Password reset (vestigial — see note above)

For users who have forgotten their password. Requires that email is configured.

```
POST /api/v1/auth/forgot-password   → sends a reset link to the email address
POST /api/v1/auth/reset-password    → uses the token from the email to set a new password
```

These routes still work and are still unlinked in the frontend (see the note at the end of [Passwordless login](#0--passwordless-login-primary-flow-since-2026-08-18)) — but since password-based `/jwt/login` was removed, there is no longer any route to actually sign in with the password this flow sets.

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

There is no `createsuperuser` CLI command yet. The current workaround is to create a user through the app's sign-up flow (email OTP — see [Passwordless login](#0--passwordless-login-primary-flow-since-2026-08-18)) or via the FastAdmin panel (`/admin`), then promote it directly in the database:

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
| POST | `/api/v1/auth/otp/request` | Anyone |
| POST | `/api/v1/auth/otp/verify` | Anyone with a valid, unexpired code |
| POST | `/api/v1/auth/register/cliente/otp` | Anyone with a valid `registration_token` |
| POST | `/api/v1/auth/register/profesional/otp` | Anyone with a valid `registration_token` |
| GET | `/api/v1/auth/google/authorize` | Anyone |
| GET | `/api/v1/auth/google/callback` | Google (redirect target, never called directly) |
| POST | `/api/v1/auth/google/session` | Anyone with a valid `google_session_token` |
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
| `REGISTRATION_TOKEN_SECRET_KEY` | Signs the short-lived token proving an email passed OTP verification, used by `/register/*/otp` |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | Access token lifetime in seconds (default: 900 = 15 minutes) |
| `REFRESH_TOKEN_EXPIRE_SECONDS` | Refresh token lifetime in seconds (default: 2592000 = 30 days) |
| `OTP_CODE_EXPIRE_SECONDS` | Email OTP code lifetime in seconds (default: 600 = 10 minutes) |
| `REGISTRATION_TOKEN_EXPIRE_SECONDS` | Registration token lifetime in seconds (default: 900 = 15 minutes) |
| `BACKEND_URL` | Backend's own public base URL, used to build the Google OAuth `redirect_uri` (must exactly match what's registered in Google Cloud Console) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google Cloud Console OAuth 2.0 Web application credentials. Leave unset to disable Google Sign-In — `/auth/google/authorize` responds 501 |
| `GOOGLE_OAUTH_STATE_EXPIRE_SECONDS` | CSRF state token lifetime in seconds (default: 600 = 10 minutes) |
| `GOOGLE_SESSION_TOKEN_EXPIRE_SECONDS` | `google_session_token` lifetime in seconds (default: 120 = 2 minutes) — only needs to survive one immediate redirect into the Next.js Route Handler |

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
A: The access token from `/api/v1/auth/otp/verify` (or `/api/v1/auth/jwt/refresh`) is used as `Authorization: Bearer <token>` on every protected request. The refresh and fingerprint tokens are cookies — you never read or send them manually; the browser attaches them automatically on calls to `/api/v1/auth/jwt/refresh` because they're scoped to that path.

**Q: I added a new page — how do I make it require login?**  
A: Put it under `/dashboard/...` and it's automatically protected — no extra code. If it has to live at a different top-level path, add that path to the `matcher` array in `proxy.ts`. There's no per-page auth check to remember; the only thing that decides whether a route is protected is whether it matches `proxy.ts`'s `matcher`. See [How page protection actually works](#how-page-protection-actually-works--and-how-to-add-a-new-protected-page).

**Q: My access token expired — what do I do?**  
A: Call `POST /api/v1/auth/jwt/refresh` (no body needed; it reads the refresh/fingerprint cookies automatically) to get a new access token. If that also returns 401, the refresh token has expired, been revoked, or reuse was detected — the user needs to log in again.

**Q: What happens if a refresh token is used twice (e.g. replayed after rotation)?**  
A: All refresh tokens for that user are immediately revoked and the request is rejected with 401. This is a deliberate theft-detection measure — see [Refresh tokens & rotation](#refresh-tokens--rotation).

**Q: How does the app know when the access token is about to expire, so it can refresh it before that happens?**  
A: This is a fair thing to wonder, because there's no alarm clock sitting on the server counting down. The trick is that a JWT already carries its own expiry time inside it — the `exp` field, buried in the token itself. It's not secret or encrypted, just signed, so anyone holding the token can peek at it. There's also a field called `expires_in` in the login/refresh response that tells you the same thing more directly — that one used to be wrong (it reported the refresh token's 30-day lifetime instead of the access token's real 15-minute one), but that's fixed now, both agree. In this app specifically, it's not client-side JavaScript doing the watching — it's `proxy.ts`, the piece of server code that already runs before every page in the dashboard loads. Right before it lets you in, it peeks at that `exp` field, and if it's about to run out, it quietly swaps in a fresh token behind the scenes before you ever notice. See [Frontend: cookie forwarding & silent refresh](#frontend-cookie-forwarding--silent-refresh) for the full picture.

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
