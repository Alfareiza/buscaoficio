"""Tests for refresh token generation, validation, and rotation."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.refresh_token_manager import RefreshTokenManager


class TestRefreshTokenGeneration:
    """Test refresh token and fingerprint generation."""

    def test_generate_tokens_returns_four_values(self) -> None:
        """Verify generate_tokens returns raw token, raw fingerprint, and two hashes."""
        (
            refresh_token,
            fingerprint_token,
            refresh_hash,
            fingerprint_hash,
        ) = RefreshTokenManager.generate_tokens()

        assert isinstance(refresh_token, str)
        assert isinstance(fingerprint_token, str)
        assert isinstance(refresh_hash, str)
        assert isinstance(fingerprint_hash, str)
        assert len(refresh_token) > 0
        assert len(fingerprint_token) > 0

    def test_generated_tokens_are_unique(self) -> None:
        """Verify each call to generate_tokens produces unique tokens."""
        tokens_1 = RefreshTokenManager.generate_tokens()
        tokens_2 = RefreshTokenManager.generate_tokens()

        assert tokens_1[0] != tokens_2[0]  # refresh tokens different
        assert tokens_1[1] != tokens_2[1]  # fingerprint tokens different
        assert tokens_1[2] != tokens_2[2]  # refresh hashes different
        assert tokens_1[3] != tokens_2[3]  # fingerprint hashes different

    def test_hash_token_is_deterministic(self) -> None:
        """Verify the same token always produces the same hash."""
        token = "test_token_value"
        hash_1 = RefreshTokenManager._hash_token(token)
        hash_2 = RefreshTokenManager._hash_token(token)

        assert hash_1 == hash_2

    def test_hash_token_produces_different_hashes_for_different_tokens(self) -> None:
        """Verify different tokens produce different hashes."""
        hash_1 = RefreshTokenManager._hash_token("token_1")
        hash_2 = RefreshTokenManager._hash_token("token_2")

        assert hash_1 != hash_2


class TestRefreshTokenStorage:
    """Test storing refresh tokens in the database."""

    @pytest.mark.asyncio
    async def test_store_refresh_token_creates_database_record(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify store_refresh_token creates a new token in the database."""
        user = await create_user()
        refresh_hash = "test_refresh_hash"
        fingerprint_hash = "test_fingerprint_hash"

        token = await RefreshTokenManager.store_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash, created_ip="127.0.0.1"
        )

        assert token.user_id == user.id
        assert token.refresh_token_hash == refresh_hash
        assert token.fingerprint_hash == fingerprint_hash
        assert token.created_ip == "127.0.0.1"
        assert token.revoked_at is None
        assert token.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_store_refresh_token_respects_lifetime(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify stored token expires at the configured lifetime."""
        user = await create_user()
        before = datetime.now(timezone.utc)

        token = await RefreshTokenManager.store_refresh_token(
            db_session, user.id, "refresh_hash", "fingerprint_hash"
        )
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(
            seconds=RefreshTokenManager.REFRESH_TOKEN_LIFETIME
        )
        expected_max = after + timedelta(
            seconds=RefreshTokenManager.REFRESH_TOKEN_LIFETIME
        )

        assert expected_min <= token.expires_at <= expected_max


class TestRefreshTokenValidation:
    """Test refresh token validation logic."""

    @pytest.mark.asyncio
    async def test_validate_valid_token_returns_token(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify validation returns the token when everything is correct."""
        user = await create_user()
        refresh_hash = "test_refresh_hash"
        fingerprint_hash = "test_fingerprint_hash"

        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )

        result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )

        assert result is not None
        assert result.user_id == user.id

    @pytest.mark.asyncio
    async def test_validate_nonexistent_token_returns_none(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify validation returns None for a token that doesn't exist."""
        user = await create_user()

        result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, "nonexistent_hash", "nonexistent_fingerprint"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_wrong_fingerprint_returns_none(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify validation fails if fingerprint hash doesn't match."""
        user = await create_user()
        refresh_hash = "test_refresh_hash"
        fingerprint_hash = "test_fingerprint_hash"

        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )

        result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, refresh_hash, "wrong_fingerprint_hash"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_revoked_token_returns_none(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify validation fails if token is revoked."""
        user = await create_user()
        refresh_hash = "test_refresh_hash"
        fingerprint_hash = "test_fingerprint_hash"

        token = await RefreshTokenManager.store_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )
        token.revoked_at = datetime.now(timezone.utc)
        await db_session.commit()

        result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_expired_token_returns_none(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify validation fails if token is expired."""
        user = await create_user()
        refresh_hash = "test_refresh_hash"
        fingerprint_hash = "test_fingerprint_hash"

        token = await RefreshTokenManager.store_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()

        result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, refresh_hash, fingerprint_hash
        )

        assert result is None


class TestRefreshTokenRotation:
    """Test token rotation (revoke old, create new)."""

    @pytest.mark.asyncio
    async def test_rotate_token_revokes_old_and_creates_new(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify rotation revokes the old token and creates a new one."""
        user = await create_user()
        old_refresh_hash = "old_refresh_hash"
        old_fingerprint_hash = "old_fingerprint_hash"

        old_token = await RefreshTokenManager.store_refresh_token(
            db_session, user.id, old_refresh_hash, old_fingerprint_hash
        )

        new_refresh_hash = "new_refresh_hash"
        new_fingerprint_hash = "new_fingerprint_hash"

        await RefreshTokenManager.rotate_refresh_token(
            db_session, old_token, new_refresh_hash, new_fingerprint_hash, "127.0.0.1"
        )

        old_result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, old_refresh_hash, old_fingerprint_hash
        )
        new_result = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, new_refresh_hash, new_fingerprint_hash
        )

        assert old_result is None
        assert new_result is not None


class TestTheftDetection:
    """Test theft detection (reuse of rotated token)."""

    @pytest.mark.asyncio
    async def test_detect_theft_revokes_all_user_tokens(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify detect_theft revokes all active tokens for the user."""
        user = await create_user()
        token_1_hash = "token_1_hash"
        token_2_hash = "token_2_hash"
        fingerprint_hash = "fingerprint_hash"

        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, token_1_hash, fingerprint_hash
        )
        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, token_2_hash, fingerprint_hash
        )

        await RefreshTokenManager.detect_theft_and_revoke(db_session, user.id)

        result_1 = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, token_1_hash, fingerprint_hash
        )
        result_2 = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, token_2_hash, fingerprint_hash
        )

        assert result_1 is None
        assert result_2 is None


class TestLogout:
    """Test logout token revocation."""

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens_invalidates_all_tokens(
        self, db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
    ) -> None:
        """Verify logout revokes all active refresh tokens for the user."""
        user = await create_user()
        token_1_hash = "token_1_hash"
        token_2_hash = "token_2_hash"
        fingerprint_hash = "fingerprint_hash"

        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, token_1_hash, fingerprint_hash
        )
        await RefreshTokenManager.store_refresh_token(
            db_session, user.id, token_2_hash, fingerprint_hash
        )

        await RefreshTokenManager.revoke_all_user_tokens(db_session, user.id)

        result_1 = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, token_1_hash, fingerprint_hash
        )
        result_2 = await RefreshTokenManager.validate_refresh_token(
            db_session, user.id, token_2_hash, fingerprint_hash
        )

        assert result_1 is None
        assert result_2 is None
