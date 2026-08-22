"""Google Sign-In via the OAuth 2.0 authorization code flow (server-side
redirect — see docs/auth.md § "Google Sign-In"). No Google JS ever runs in
the browser; the backend drives the whole exchange, matching how the rest
of this app's auth is server-mediated.

Design note: httpx-oauth's GoogleOAuth2.get_id_email()/get_profile() go
through Google's People API, which needs a different scope and doesn't
expose `email_verified` or a stable OIDC `sub`. Instead, this module
requests the `openid` scope so Google's token endpoint returns a signed
`id_token` (a JWT) alongside the access token, and verifies+decodes that
JWT directly against Google's published JWKS — one HTTP round trip
(the token exchange) instead of two, and it's the standard OIDC pattern.
"""

from dataclasses import dataclass
from typing import Optional

import secrets

import jwt
from fastapi_users.jwt import decode_jwt, generate_jwt
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import GetAccessTokenError

from .config import logger, settings

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_OAUTH_SCOPES = ["openid", "email", "profile"]
GOOGLE_STATE_AUDIENCE = "buscaoficio:google-oauth-state"
GOOGLE_SESSION_AUDIENCE = "buscaoficio:google-session"
# PyJWT validates iat/exp/nbf against the local wall clock with zero
# tolerance by default. A few seconds of drift between this server's clock
# and Google's is normal — and on Docker Desktop for Mac, the container
# clock can lag noticeably right after the host sleeps/wakes, until the VM
# resyncs. Without leeway, that drift alone fails every login with
# "ImmatureSignatureError: The token is not yet valid (iat)", indistinguishable
# from a real security problem. 30s absorbs realistic drift without
# meaningfully loosening the token's actual validity window.
GOOGLE_ID_TOKEN_LEEWAY_SECONDS = 30

_jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URI)


@dataclass
class GoogleProfile:
    sub: str
    email: str
    email_verified: bool
    name: Optional[str]
    picture: Optional[str] = None


class GoogleOAuthError(Exception):
    """Raised when the Google code exchange or ID token verification fails."""


class GoogleOAuthManager:
    """Builds the Google consent-screen URL and exchanges an authorization
    code for a verified user profile. Stateless — every call constructs its
    own GoogleOAuth2 client from settings, since there's no per-request
    state to hold onto beyond the client id/secret."""

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)

    @staticmethod
    def issue_state() -> str:
        """Sign a short-lived CSRF state token for the authorize→callback
        round trip. A random nonce claim (rather than signing an empty
        payload) keeps every issued token unique even if issued in the same
        second. No server-side session store exists in this stateless API,
        so the state itself carries its own proof instead of being looked
        up server-side."""
        return generate_jwt(
            {"nonce": secrets.token_urlsafe(16), "aud": GOOGLE_STATE_AUDIENCE},
            settings.REGISTRATION_TOKEN_SECRET_KEY,
            settings.GOOGLE_OAUTH_STATE_EXPIRE_SECONDS,
        )

    @staticmethod
    def verify_state(state: str) -> bool:
        try:
            decode_jwt(
                state, settings.REGISTRATION_TOKEN_SECRET_KEY, [GOOGLE_STATE_AUDIENCE]
            )
        except jwt.PyJWTError:
            return False
        return True

    @staticmethod
    def issue_session_token(user_id, picture: Optional[str] = None) -> str:
        """Sign a short-lived, single-purpose token proving `user_id` just
        completed Google verification in /google/callback. Consumed
        immediately by POST /auth/google/session, which is called by a
        Next.js Server Action — not by /google/callback itself — because
        cookies must be set by the Next.js server on its own origin
        (app.buscaoficio.co), the same way every other login in this app
        works (see docs/auth.md's cookie-forwarding section). FastAPI
        (api.buscaoficio.co) setting cookies directly on a browser redirect
        would land them on the wrong origin.

        `picture` rides along so /auth/google/session can hand it back to
        the frontend — it's never persisted on the User row (display-only
        hint for the "Welcome back" card, re-fetched fresh on every Google
        login rather than treated as durable profile data)."""
        payload = {"user_id": str(user_id), "aud": GOOGLE_SESSION_AUDIENCE}
        if picture is not None:
            payload["picture"] = picture
        return generate_jwt(
            payload,
            settings.REGISTRATION_TOKEN_SECRET_KEY,
            settings.GOOGLE_SESSION_TOKEN_EXPIRE_SECONDS,
        )

    @staticmethod
    def verify_session_token(token: str) -> Optional[dict]:
        try:
            return decode_jwt(
                token, settings.REGISTRATION_TOKEN_SECRET_KEY, [GOOGLE_SESSION_AUDIENCE]
            )
        except jwt.PyJWTError:
            return None

    @classmethod
    def _client(cls) -> GoogleOAuth2:
        return GoogleOAuth2(
            settings.GOOGLE_OAUTH_CLIENT_ID,
            settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=GOOGLE_OAUTH_SCOPES,
        )

    @classmethod
    def _redirect_uri(cls) -> str:
        return f"{settings.BACKEND_URL}/api/v1/auth/google/callback"

    @classmethod
    async def get_authorization_url(cls, state: str) -> str:
        return await cls._client().get_authorization_url(
            cls._redirect_uri(),
            state=state,
            scope=GOOGLE_OAUTH_SCOPES,
        )

    @classmethod
    async def exchange_code_for_profile(cls, code: str) -> GoogleProfile:
        """Exchange an authorization `code` for Google's id_token and
        return the verified profile. Raises GoogleOAuthError on any
        failure (bad/expired code, signature/audience/issuer mismatch)."""
        try:
            token = await cls._client().get_access_token(code, cls._redirect_uri())
        except GetAccessTokenError as exc:
            # exc.response carries Google's actual error body (e.g.
            # "redirect_uri_mismatch", "invalid_grant" for a reused/expired
            # code) — log it here, since the generic GoogleOAuthError raised
            # below is all the caller (google_callback) sees, and a bare
            # "code exchange failed" warning gives no way to diagnose which
            # of those very different problems actually happened.
            body = exc.response.text if exc.response is not None else None
            status_code = exc.response.status_code if exc.response is not None else None
            logger.error(
                f"Google token exchange failed: status={status_code} body={body!r}"
            )
            raise GoogleOAuthError("Failed to exchange authorization code") from exc

        id_token = token.get("id_token")
        if not id_token:
            raise GoogleOAuthError("Google token response missing id_token")

        try:
            signing_key = _jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.GOOGLE_OAUTH_CLIENT_ID,
                leeway=GOOGLE_ID_TOKEN_LEEWAY_SECONDS,
            )
        except jwt.PyJWTError as exc:
            # Same reasoning as the token-exchange log above: PyJWTError's
            # subclass and message (e.g. "Signature has expired", "Invalid
            # audience", "Unable to find a signing key...") is the actual
            # diagnostic signal — GoogleOAuthError's generic message alone
            # doesn't say whether this is a clock-skew, wrong-client-id, or
            # stale-JWKS-cache problem.
            logger.error(f"Google id_token verification failed: {exc!r}")
            raise GoogleOAuthError("Invalid Google id_token") from exc

        # PyJWT's built-in `issuer=` check only accepts a single value, but
        # Google's id_tokens use two interchangeable issuer strings — check
        # membership manually instead.
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise GoogleOAuthError("Invalid Google id_token issuer")

        sub = claims.get("sub")
        email = claims.get("email")
        if not sub or not email:
            raise GoogleOAuthError("Google id_token missing sub/email claims")

        return GoogleProfile(
            sub=sub,
            email=email,
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )
