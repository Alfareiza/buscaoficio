"""Integration tests for the login -> refresh -> logout flow with refresh token rotation."""

from collections.abc import Awaitable, Callable

import pytest
from fastapi import status
from sqlalchemy import select

from app.config import settings
from app.models import RefreshToken, User
from app.refresh_token_manager import RefreshTokenManager

DEFAULT_PASSWORD = "TestPassword123#"


async def _login(test_client, email: str, password: str = DEFAULT_PASSWORD):
    """Log in and return the httpx response (with cookies set on the client)."""
    return await test_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
    )


class TestLoginIssuesRefreshToken:
    """Verify login creates a refresh token row and sets cookies."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_returns_access_token(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        response = await _login(test_client, user.email)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_expires_in_reflects_access_token_lifetime(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Regression test: expires_in must describe the access token, not the refresh token."""
        user = await create_user()
        response = await _login(test_client, user.email)

        body = response.json()
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_SECONDS
        assert body["expires_in"] != RefreshTokenManager.REFRESH_TOKEN_LIFETIME

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_sets_refresh_and_fingerprint_cookies(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        response = await _login(test_client, user.email)

        assert "refreshToken" in response.cookies
        assert "fingerprintToken" in response.cookies

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_creates_refresh_token_db_row(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        user = await create_user()
        await _login(test_client, user.email)

        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        tokens = result.scalars().all()

        assert len(tokens) == 1
        assert tokens[0].revoked_at is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_bad_credentials_does_not_create_refresh_token(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        user = await create_user()
        response = await _login(test_client, user.email, password="WrongPassword1#")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        assert result.scalars().all() == []


class TestRefreshEndpoint:
    """Verify /auth/jwt/refresh rotates tokens correctly."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_with_valid_cookies_returns_new_access_token(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        await _login(test_client, user.email)

        refresh_response = await test_client.post("/api/v1/auth/jwt/refresh")

        assert refresh_response.status_code == status.HTTP_200_OK
        body = refresh_response.json()
        assert isinstance(body["access_token"], str) and body["access_token"]
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_expires_in_reflects_access_token_lifetime(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Regression test: expires_in must describe the access token, not the refresh token."""
        user = await create_user()
        await _login(test_client, user.email)

        refresh_response = await test_client.post("/api/v1/auth/jwt/refresh")

        body = refresh_response.json()
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_SECONDS
        assert body["expires_in"] != RefreshTokenManager.REFRESH_TOKEN_LIFETIME

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_rotates_cookies(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        login_response = await _login(test_client, user.email)
        old_refresh_cookie = login_response.cookies.get("refreshToken")

        refresh_response = await test_client.post("/api/v1/auth/jwt/refresh")

        new_refresh_cookie = refresh_response.cookies.get("refreshToken")
        assert new_refresh_cookie is not None
        assert new_refresh_cookie != old_refresh_cookie

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_without_cookies_returns_401(self, test_client) -> None:
        response = await test_client.post("/api/v1/auth/jwt/refresh")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio(loop_scope="function")
    async def test_reusing_rotated_refresh_token_is_rejected(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        """Simulates theft detection: an old (already-rotated) refresh token is reused."""
        user = await create_user()
        await _login(test_client, user.email)

        old_cookies = dict(test_client.cookies)

        first_refresh = await test_client.post("/api/v1/auth/jwt/refresh")
        assert first_refresh.status_code == status.HTTP_200_OK

        test_client.cookies.set("refreshToken", old_cookies["refreshToken"])
        test_client.cookies.set("fingerprintToken", old_cookies["fingerprintToken"])

        second_refresh = await test_client.post("/api/v1/auth/jwt/refresh")

        assert second_refresh.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio(loop_scope="function")
    async def test_reusing_rotated_refresh_token_revokes_all_sessions(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        """Theft detection should kill ALL active sessions for the user, not just the reused one."""
        user = await create_user()
        await _login(test_client, user.email)
        old_cookies = dict(test_client.cookies)

        await test_client.post("/api/v1/auth/jwt/refresh")
        newest_cookies = dict(test_client.cookies)

        test_client.cookies.set("refreshToken", old_cookies["refreshToken"])
        test_client.cookies.set("fingerprintToken", old_cookies["fingerprintToken"])
        await test_client.post("/api/v1/auth/jwt/refresh")

        test_client.cookies.set("refreshToken", newest_cookies["refreshToken"])
        test_client.cookies.set("fingerprintToken", newest_cookies["fingerprintToken"])
        third_refresh = await test_client.post("/api/v1/auth/jwt/refresh")

        assert third_refresh.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_with_wrong_fingerprint_returns_401(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        await _login(test_client, user.email)

        test_client.cookies.set("fingerprintToken", "tampered-fingerprint-value")

        response = await test_client.post("/api/v1/auth/jwt/refresh")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogoutInvalidation:
    """Verify logout revokes refresh tokens server-side."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_logout_revokes_refresh_token_in_db(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        user = await create_user()
        login_response = await _login(test_client, user.email)
        access_token = login_response.json()["access_token"]

        await test_client.post(
            "/api/v1/auth/jwt/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        tokens = result.scalars().all()

        assert all(token.revoked_at is not None for token in tokens)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_after_logout_returns_401(
        self, test_client, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        user = await create_user()
        login_response = await _login(test_client, user.email)
        access_token = login_response.json()["access_token"]

        await test_client.post(
            "/api/v1/auth/jwt/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        refresh_response = await test_client.post("/api/v1/auth/jwt/refresh")

        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio(loop_scope="function")
    async def test_logout_from_one_session_invalidates_other_sessions(
        self,
        test_client,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        """Simulates multi-device logout: Device A logs out, Device B's refresh token dies too."""
        user = await create_user()

        login_device_a = await _login(test_client, user.email)
        device_a_access_token = login_device_a.json()["access_token"]

        test_client.cookies.clear()
        await _login(test_client, user.email)
        device_b_cookies = dict(test_client.cookies)

        await test_client.post(
            "/api/v1/auth/jwt/logout",
            headers={"Authorization": f"Bearer {device_a_access_token}"},
        )

        test_client.cookies.set("refreshToken", device_b_cookies["refreshToken"])
        test_client.cookies.set(
            "fingerprintToken", device_b_cookies["fingerprintToken"]
        )
        device_b_refresh = await test_client.post("/api/v1/auth/jwt/refresh")

        assert device_b_refresh.status_code == status.HTTP_401_UNAUTHORIZED
