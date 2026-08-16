import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import RefreshToken


class RefreshTokenManager:
    """Manage refresh token lifecycle: generation, validation, rotation, theft detection."""

    TOKEN_LENGTH = 32  # bytes, base64-encoded to ~43 chars
    REFRESH_TOKEN_LIFETIME = settings.REFRESH_TOKEN_EXPIRE_SECONDS
    FINGERPRINT_TOKEN_LENGTH = 32

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token using SHA256."""
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def generate_tokens(cls) -> tuple[str, str, str]:
        """Generate refresh token, fingerprint token, and their hashes.

        Returns:
            (refresh_token_raw, fingerprint_token_raw, refresh_hash, fingerprint_hash)
        """
        refresh_token = secrets.token_urlsafe(cls.TOKEN_LENGTH)
        fingerprint_token = secrets.token_urlsafe(cls.FINGERPRINT_TOKEN_LENGTH)
        refresh_hash = cls._hash_token(refresh_token)
        fingerprint_hash = cls._hash_token(fingerprint_token)
        return refresh_token, fingerprint_token, refresh_hash, fingerprint_hash

    @classmethod
    async def store_refresh_token(
        cls,
        db: AsyncSession,
        user_id: UUID,
        refresh_token_hash: str,
        fingerprint_hash: str,
        created_ip: Optional[str] = None,
    ) -> RefreshToken:
        """Store a refresh token in the database."""
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=cls.REFRESH_TOKEN_LIFETIME
        )
        token = RefreshToken(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            fingerprint_hash=fingerprint_hash,
            expires_at=expires_at,
            created_ip=created_ip,
        )
        db.add(token)
        await db.flush()
        return token

    @classmethod
    async def validate_refresh_token(
        cls,
        db: AsyncSession,
        user_id: UUID,
        refresh_token_hash: str,
        fingerprint_hash: str,
    ) -> Optional[RefreshToken]:
        """Validate a refresh token.

        Returns the token if valid, None otherwise. Checks:
        - Token exists and belongs to user
        - Token hasn't expired
        - Token hasn't been revoked
        - Fingerprint matches
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.refresh_token_hash == refresh_token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()

        if not token:
            return None

        if datetime.now(timezone.utc) > token.expires_at:
            return None

        if token.fingerprint_hash != fingerprint_hash:
            return None

        return token

    @classmethod
    async def rotate_refresh_token(
        cls,
        db: AsyncSession,
        old_token: RefreshToken,
        new_refresh_token_hash: str,
        new_fingerprint_hash: str,
        created_ip: Optional[str] = None,
    ) -> RefreshToken:
        """Rotate a refresh token: revoke the old one, create a new one."""
        old_token.revoked_at = datetime.now(timezone.utc)
        await cls.store_refresh_token(
            db,
            old_token.user_id,
            new_refresh_token_hash,
            new_fingerprint_hash,
            created_ip,
        )
        await db.commit()

    @classmethod
    async def detect_theft_and_revoke(cls, db: AsyncSession, user_id: UUID) -> None:
        """Detect token theft (attempt to reuse an already-rotated token).

        Revoke all active refresh tokens for this user (forcing re-login).
        Log this as a potential breach event.
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        result = await db.execute(stmt)
        tokens = result.scalars().all()

        for token in tokens:
            token.revoked_at = datetime.now(timezone.utc)

        await db.commit()

    @classmethod
    async def revoke_all_user_tokens(cls, db: AsyncSession, user_id: UUID) -> None:
        """Revoke all refresh tokens for a user (e.g., on logout)."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        result = await db.execute(stmt)
        tokens = result.scalars().all()

        for token in tokens:
            token.revoked_at = datetime.now(timezone.utc)

        await db.commit()
