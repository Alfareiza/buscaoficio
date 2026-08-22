"""Unit tests for GoogleOAuthManager.exchange_code_for_profile's id_token
verification — specifically the leeway fix for clock skew between this
server and Google's.

Regression context: a real login failed in production-like conditions with
`ImmatureSignatureError: The token is not yet valid (iat)` — PyJWT validates
iat/exp with zero tolerance by default, and Docker Desktop's Linux VM clock
can drift a few seconds (or more, right after the host sleeps/wakes) from
the host/Google's clock. These tests build a real signed RS256 token (same
shape as Google's id_token) with a controlled `iat` offset, so they fail the
same way the real bug did if GOOGLE_ID_TOKEN_LEEWAY_SECONDS regresses to 0.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import OAuth2Token

from app.config import settings
from app.google_oauth_manager import (
    GOOGLE_ID_TOKEN_LEEWAY_SECONDS,
    GoogleOAuthError,
    GoogleOAuthManager,
)

TEST_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _FakeSigningKey:
    key: object


@pytest.fixture(autouse=True)
def _configured(mocker):
    mocker.patch.object(settings, "GOOGLE_OAUTH_CLIENT_ID", TEST_CLIENT_ID)
    mocker.patch.object(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")


def _sign_id_token(private_key, *, iat_offset_seconds: float, **claim_overrides) -> str:
    now = datetime.now(timezone.utc)
    iat = now + timedelta(seconds=iat_offset_seconds)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": TEST_CLIENT_ID,
        "sub": "108000000000000000001",
        "email": "alfonso@example.com",
        "email_verified": True,
        "name": "Alfonso Areiza",
        "iat": iat,
        "exp": iat + timedelta(hours=1),
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})


def _mock_google_round_trip(mocker, id_token: str) -> None:
    """Mocks the two network calls exchange_code_for_profile makes: the
    token-exchange POST (get_access_token) and the JWKS lookup (PyJWKClient),
    without touching the actual RS256/claims verification — that's the real
    code under test."""
    mocker.patch.object(
        GoogleOAuth2,
        "get_access_token",
        mocker.AsyncMock(return_value=OAuth2Token({"id_token": id_token})),
    )
    private_key = _RSA_KEY
    mocker.patch(
        "app.google_oauth_manager._jwks_client.get_signing_key_from_jwt",
        return_value=_FakeSigningKey(key=private_key.public_key()),
    )


class TestClockSkewLeeway:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_iat_slightly_in_the_future_is_accepted_within_leeway(
        self, mocker
    ) -> None:
        # Half the configured leeway — must be well inside the tolerance.
        id_token = _sign_id_token(
            _RSA_KEY, iat_offset_seconds=GOOGLE_ID_TOKEN_LEEWAY_SECONDS / 2
        )
        _mock_google_round_trip(mocker, id_token)

        profile = await GoogleOAuthManager.exchange_code_for_profile("auth-code")

        assert profile.email == "alfonso@example.com"
        assert profile.sub == "108000000000000000001"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_iat_far_in_the_future_is_still_rejected(self, mocker) -> None:
        # Comfortably outside the leeway — this must still fail, or the
        # leeway would be silently masking a genuinely invalid/forged token.
        id_token = _sign_id_token(
            _RSA_KEY, iat_offset_seconds=GOOGLE_ID_TOKEN_LEEWAY_SECONDS * 10
        )
        _mock_google_round_trip(mocker, id_token)

        with pytest.raises(GoogleOAuthError, match="Invalid Google id_token"):
            await GoogleOAuthManager.exchange_code_for_profile("auth-code")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_expired_token_is_rejected_even_within_leeway_of_now(
        self, mocker
    ) -> None:
        # exp in the past, outside leeway — leeway must not make a stale
        # token valid indefinitely.
        id_token = _sign_id_token(
            _RSA_KEY,
            iat_offset_seconds=-3600,
            exp=datetime.now(timezone.utc)
            - timedelta(seconds=GOOGLE_ID_TOKEN_LEEWAY_SECONDS * 10),
        )
        _mock_google_round_trip(mocker, id_token)

        with pytest.raises(GoogleOAuthError, match="Invalid Google id_token"):
            await GoogleOAuthManager.exchange_code_for_profile("auth-code")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_logs_the_real_pyjwt_error_on_failure(self, mocker, caplog) -> None:
        id_token = _sign_id_token(
            _RSA_KEY, iat_offset_seconds=GOOGLE_ID_TOKEN_LEEWAY_SECONDS * 10
        )
        _mock_google_round_trip(mocker, id_token)

        with caplog.at_level("ERROR", logger="buscaoficio"):
            with pytest.raises(GoogleOAuthError):
                await GoogleOAuthManager.exchange_code_for_profile("auth-code")

        # Regression guard for the original bug: this message (not just a
        # generic "Invalid Google id_token") is what actually let us
        # diagnose the real production failure as clock skew rather than a
        # forged/tampered token.
        assert "ImmatureSignatureError" in caplog.text
