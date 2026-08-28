"""Integration tests for Google Sign-In (OAuth 2.0 authorization code flow).

Google itself is never called — GoogleOAuthManager.exchange_code_for_profile
is the network boundary and is mocked throughout, same as OTP tests mock the
outbound email send.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.google_oauth_manager import GoogleOAuthError, GoogleOAuthManager, GoogleProfile
from app.models import User
from app.otp_manager import OtpManager

NEW_EMAIL = "new-google-user@example.com"
PICTURE_URL = "https://lh3.googleusercontent.com/a/pic.jpg"


@pytest.fixture(autouse=True)
def configured_google_oauth(mocker):
    """Every test needs Google Sign-In "configured" — GoogleOAuthManager
    checks these two settings before doing anything."""
    mocker.patch.object(GoogleOAuthManager, "is_configured", return_value=True)


@pytest.fixture
def mock_send_otp_email(mocker):
    """Only needed by the OTP-vs-Google contrast test below — never hit
    real SMTP. Same fixture as tests/routes/test_auth_otp.py."""
    return mocker.patch("app.routes.auth.send_otp_code_email", mocker.AsyncMock())


def _mock_profile(mocker, **overrides):
    defaults = dict(
        sub="google-sub-123",
        email=NEW_EMAIL,
        email_verified=True,
        name="Nueva Persona",
        picture=PICTURE_URL,
    )
    defaults.update(overrides)
    return mocker.patch.object(
        GoogleOAuthManager,
        "exchange_code_for_profile",
        mocker.AsyncMock(return_value=GoogleProfile(**defaults)),
    )


class TestGoogleAuthorize:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_redirects_to_google(self, test_client) -> None:
        response = await test_client.get(
            "/api/v1/auth/google/authorize", follow_redirects=False
        )
        assert response.status_code == status.HTTP_302_FOUND
        location = urlparse(response.headers["location"])
        assert location.hostname == "accounts.google.com"
        assert "state" in parse_qs(location.query)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_501_when_not_configured(
        self, test_client, mocker, caplog
    ) -> None:
        mocker.patch.object(GoogleOAuthManager, "is_configured", return_value=False)
        with caplog.at_level("WARNING", logger="buscaoficio"):
            response = await test_client.get(
                "/api/v1/auth/google/authorize", follow_redirects=False
            )
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        assert "not configured" in caplog.text


class TestGoogleCallbackNewEmail:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_new_email_redirects_with_registration_token(
        self, test_client, mocker
    ) -> None:
        _mock_profile(mocker)
        state = GoogleOAuthManager.issue_state()

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        location = urlparse(response.headers["location"])
        assert location.path == "/register"
        query = parse_qs(location.query)
        assert query["provider"] == ["google"]
        assert query["name"] == ["Nueva Persona"]

        payload = OtpManager.verify_registration_token(query["registration_token"][0])
        assert payload["email"] == NEW_EMAIL
        assert payload["google_sub"] == "google-sub-123"
        assert payload["nombre_completo"] == "Nueva Persona"
        assert payload["picture"] == PICTURE_URL

    @pytest.mark.asyncio(loop_scope="function")
    async def test_registration_token_completes_signup_with_google_sub(
        self, test_client, mocker, db_session
    ) -> None:
        _mock_profile(mocker)
        state = GoogleOAuthManager.issue_state()
        callback = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        registration_token = parse_qs(urlparse(callback.headers["location"]).query)[
            "registration_token"
        ][0]

        response = await test_client.post(
            "/api/v1/auth/register/cliente/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Nueva Persona",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["nombre_completo"] == "Nueva Persona"
        assert body["email"] == NEW_EMAIL
        assert body["picture"] == PICTURE_URL

        result = await db_session.execute(select(User).where(User.email == NEW_EMAIL))
        user = result.scalar_one()
        assert user.google_sub == "google-sub-123"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_otp_registration_response_has_no_picture_key(
        self, test_client, mock_send_otp_email
    ) -> None:
        """A plain OTP registration (no google_sub on the registration_token)
        must not include a `picture` key at all — its presence is the
        frontend's sole signal that a login/registration was Google-backed
        (see otp-auth-action.ts's persistSession)."""
        otp_email = "otp-only-user@example.com"
        code_response = await test_client.post(
            "/api/v1/auth/otp/request", json={"email": otp_email}
        )
        assert code_response.status_code == status.HTTP_202_ACCEPTED
        code = mock_send_otp_email.call_args[0][1]

        verify = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": otp_email, "code": code}
        )
        registration_token = verify.json()["registration_token"]

        response = await test_client.post(
            "/api/v1/auth/register/cliente/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Solo OTP",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert "picture" not in response.json()


class TestGoogleCallbackExistingUser:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_matched_by_google_sub_redirects_with_session_token(
        self,
        test_client,
        mocker,
        create_user: Callable[..., Awaitable[User]],
        db_session,
    ) -> None:
        user = await create_user(email="linked@example.com")
        user.google_sub = "google-sub-456"
        db_session.add(user)
        await db_session.commit()

        _mock_profile(mocker, sub="google-sub-456", email=user.email)
        state = GoogleOAuthManager.issue_state()

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        # Hands off to the Next.js Route Handler, not a page — that's what
        # keeps the browser from rendering anything between Google and
        # /dashboard (see app/api/auth/google/complete/route.ts).
        location = urlparse(response.headers["location"])
        assert location.path == "/api/auth/google/complete"
        query = parse_qs(location.query)
        assert "google_session_token" in query
        session_payload = GoogleOAuthManager.verify_session_token(
            query["google_session_token"][0]
        )
        assert session_payload["picture"] == PICTURE_URL

    @pytest.mark.asyncio(loop_scope="function")
    async def test_inactive_user_redirects_to_login_error_and_logs(
        self,
        test_client,
        mocker,
        create_user: Callable[..., Awaitable[User]],
        caplog,
    ) -> None:
        user = await create_user(email="inactive@example.com", is_active=False)
        _mock_profile(mocker, sub="google-sub-inactive", email=user.email)
        state = GoogleOAuthManager.issue_state()

        with caplog.at_level("WARNING", logger="buscaoficio"):
            response = await test_client.get(
                "/api/v1/auth/google/callback",
                params={"code": "auth-code", "state": state},
                follow_redirects=False,
            )

        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]
        assert str(user.id) in caplog.text
        assert "inactive" in caplog.text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_deleted_user_is_not_linked_and_does_not_register(
        self,
        test_client,
        mocker,
        create_user: Callable[..., Awaitable[User]],
        authenticated_superuser: dict,
        db_session,
        caplog,
    ) -> None:
        user = await create_user(email="deleted-google@example.com")
        await test_client.delete(
            f"/api/v1/users/{user.id}",
            headers=authenticated_superuser["headers"],
        )
        _mock_profile(mocker, sub="google-sub-deleted", email=user.email)
        state = GoogleOAuthManager.issue_state()

        with caplog.at_level("WARNING", logger="buscaoficio"):
            response = await test_client.get(
                "/api/v1/auth/google/callback",
                params={"code": "auth-code", "state": state},
                follow_redirects=False,
            )

        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]
        leftover = (
            await db_session.execute(
                select(User)
                .where(User.id == user.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert leftover.google_sub is None
        assert leftover.deleted_at is not None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_matched_by_email_backfills_google_sub(
        self,
        test_client,
        mocker,
        create_user: Callable[..., Awaitable[User]],
        db_session,
    ) -> None:
        user = await create_user(email="otp-created@example.com")
        assert user.google_sub is None

        _mock_profile(mocker, sub="google-sub-789", email=user.email)
        state = GoogleOAuthManager.issue_state()

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert "google_session_token" in response.headers["location"]

        result = await db_session.execute(select(User).where(User.id == user.id))
        refreshed = result.scalar_one()
        assert refreshed.google_sub == "google-sub-789"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_concurrent_linking_race_recovers_instead_of_500ing(
        self,
        test_client,
        mocker,
        create_user: Callable[..., Awaitable[User]],
        db_session,
        engine,
    ) -> None:
        """Two concurrent callbacks for the same not-yet-linked email both
        pass the `google_sub is None` check, then race to commit. Simulates
        the loser's commit hitting the real unique constraint — via a
        genuinely separate connection committing first, not a stubbed
        exception — and asserts the loser recovers into a normal login
        instead of surfacing an unhandled 500."""
        user = await create_user(email="race@example.com")
        assert user.google_sub is None

        _mock_profile(mocker, sub="google-sub-race", email=user.email)
        state = GoogleOAuthManager.issue_state()

        async def racy_commit():
            # The "winner": a wholly separate transaction links the same
            # row first, so this request's own commit below genuinely
            # violates the unique constraint rather than merely simulating
            # the error.
            async with AsyncSession(engine) as other_session:
                await other_session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(google_sub="google-sub-race")
                )
                await other_session.commit()
            raise IntegrityError(
                "duplicate key value violates unique constraint "
                '"usuarios_google_sub_key"',
                {},
                Exception("duplicate key"),
            )

        mocker.patch.object(db_session, "commit", side_effect=racy_commit)

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        location = urlparse(response.headers["location"])
        assert location.path == "/api/auth/google/complete"
        assert "google_session_token" in parse_qs(location.query)

        result = await db_session.execute(select(User).where(User.id == user.id))
        refreshed = result.scalar_one()
        assert refreshed.google_sub == "google-sub-race"


class TestGoogleCallbackFailures:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_state_redirects_to_login_error(
        self, test_client, mocker
    ) -> None:
        _mock_profile(mocker)
        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": "not-a-real-state"},
            follow_redirects=False,
        )
        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_unverified_email_redirects_to_login_error(
        self, test_client, mocker
    ) -> None:
        _mock_profile(mocker, email_verified=False)
        state = GoogleOAuthManager.issue_state()

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        location = urlparse(response.headers["location"])
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_google_error_param_redirects_to_login_error(
        self, test_client
    ) -> None:
        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        location = urlparse(response.headers["location"])
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_code_exchange_failure_redirects_to_login_error(
        self, test_client, mocker
    ) -> None:
        mocker.patch.object(
            GoogleOAuthManager,
            "exchange_code_for_profile",
            mocker.AsyncMock(side_effect=GoogleOAuthError("bad code")),
        )
        state = GoogleOAuthManager.issue_state()

        response = await test_client.get(
            "/api/v1/auth/google/callback",
            params={"code": "bad-code", "state": state},
            follow_redirects=False,
        )
        location = urlparse(response.headers["location"])
        assert parse_qs(location.query)["error"] == ["google_auth_failed"]


class TestGoogleSession:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_valid_session_token_logs_in(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user(email="session@example.com")
        session_token = GoogleOAuthManager.issue_session_token(user.id)

        response = await test_client.post(
            "/api/v1/auth/google/session",
            json={"google_session_token": session_token},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "existing_user"
        assert "access_token" in body
        assert body["nombre_completo"] == user.nombre_completo
        assert body["email"] == user.email
        assert body["picture"] is None
        assert "refreshToken" in response.cookies
        assert "fingerprintToken" in response.cookies

    @pytest.mark.asyncio(loop_scope="function")
    async def test_valid_session_token_with_picture_returns_it(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user(email="session-with-photo@example.com")
        session_token = GoogleOAuthManager.issue_session_token(
            user.id, picture=PICTURE_URL
        )

        response = await test_client.post(
            "/api/v1/auth/google/session",
            json={"google_session_token": session_token},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["picture"] == PICTURE_URL

    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_session_token_returns_400_and_logs(
        self, test_client, caplog
    ) -> None:
        with caplog.at_level("WARNING", logger="buscaoficio"):
            response = await test_client.post(
                "/api/v1/auth/google/session",
                json={"google_session_token": "not-a-real-token"},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid/expired google_session_token" in caplog.text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_inactive_user_session_token_returns_400_and_logs(
        self, test_client, create_user: Callable[..., Awaitable[User]], caplog
    ) -> None:
        user = await create_user(email="inactive-session@example.com", is_active=False)
        session_token = GoogleOAuthManager.issue_session_token(user.id)

        with caplog.at_level("WARNING", logger="buscaoficio"):
            response = await test_client.post(
                "/api/v1/auth/google/session",
                json={"google_session_token": session_token},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(user.id) in caplog.text
        assert "not found or inactive" in caplog.text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_session_token_cannot_be_replayed(
        self, test_client, create_user: Callable[..., Awaitable[User]], caplog
    ) -> None:
        """A google_session_token is a bearer credential that briefly rides
        in a redirect URL (see issue_session_token's docstring) — if a copy
        leaks (request logs, Sentry tracing) within its 2-minute lifetime,
        it must not be usable more than once."""
        user = await create_user(email="replay@example.com")
        session_token = GoogleOAuthManager.issue_session_token(user.id)

        first = await test_client.post(
            "/api/v1/auth/google/session",
            json={"google_session_token": session_token},
        )
        assert first.status_code == status.HTTP_200_OK

        with caplog.at_level("WARNING", logger="buscaoficio"):
            second = await test_client.post(
                "/api/v1/auth/google/session",
                json={"google_session_token": session_token},
            )

        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert "replay detected" in caplog.text
        assert str(user.id) in caplog.text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_two_different_session_tokens_for_same_user_both_work(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Replay protection is per-token (per jti), not per-user — logging
        in via Google twice in a row (two distinct callback round trips)
        must still work."""
        user = await create_user(email="two-logins@example.com")

        first_token = GoogleOAuthManager.issue_session_token(user.id)
        second_token = GoogleOAuthManager.issue_session_token(user.id)
        assert first_token != second_token

        first = await test_client.post(
            "/api/v1/auth/google/session",
            json={"google_session_token": first_token},
        )
        second = await test_client.post(
            "/api/v1/auth/google/session",
            json={"google_session_token": second_token},
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
