import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi_users.jwt import decode_jwt, generate_jwt
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import EmailOtp

REGISTRATION_TOKEN_AUDIENCE = "buscaoficio:register"


class OtpManager:
    """Manage passwordless email-OTP lifecycle: generation, verification,
    and the short-lived registration token issued after a new email is
    verified but before an account exists (see docs/auth.md)."""

    CODE_LENGTH = 6
    MAX_ATTEMPTS = 5
    RESEND_COOLDOWN_SECONDS = 60
    OTP_LIFETIME = settings.OTP_CODE_EXPIRE_SECONDS

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def _generate_code(cls) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(cls.CODE_LENGTH))

    @classmethod
    async def request_code(
        cls, db: AsyncSession, email: str, ip: Optional[str] = None
    ) -> Optional[str]:
        """Generate and store a new OTP for `email`, invalidating any prior
        outstanding code. Returns the raw code to send, or None if a code was
        already issued within the resend cooldown (caller should still return
        a generic success response either way — anti-enumeration)."""
        now = datetime.now(timezone.utc)

        stmt = select(EmailOtp).where(
            EmailOtp.email == email, EmailOtp.consumed_at.is_(None)
        )
        result = await db.execute(stmt)
        outstanding = result.scalars().all()

        for row in outstanding:
            age_seconds = (now - row.creado_en).total_seconds()
            if row.expires_at > now and age_seconds < cls.RESEND_COOLDOWN_SECONDS:
                return None
            row.consumed_at = now  # invalidate stale/replaced codes

        code = cls._generate_code()
        otp = EmailOtp(
            email=email,
            code_hash=cls._hash_code(code),
            expires_at=now + timedelta(seconds=cls.OTP_LIFETIME),
            created_ip=ip,
        )
        db.add(otp)
        await db.commit()
        return code

    @classmethod
    async def verify_code(cls, db: AsyncSession, email: str, code: str) -> bool:
        """Validate `code` for `email`. Returns True and consumes the code on
        success. Increments attempts and returns False on mismatch, expiry,
        absence, or after MAX_ATTEMPTS has been exceeded."""
        now = datetime.now(timezone.utc)

        stmt = (
            select(EmailOtp)
            .where(
                EmailOtp.email == email,
                EmailOtp.consumed_at.is_(None),
                EmailOtp.expires_at > now,
            )
            .order_by(EmailOtp.creado_en.desc())
        )
        result = await db.execute(stmt)
        otp = result.scalars().first()

        if not otp or otp.attempts >= cls.MAX_ATTEMPTS:
            return False

        if otp.code_hash != cls._hash_code(code):
            otp.attempts += 1
            await db.commit()
            return False

        otp.consumed_at = now
        await db.commit()
        return True

    @classmethod
    def issue_registration_token(cls, email: str) -> str:
        """Sign a short-lived token proving `email` passed OTP verification,
        without creating a usuario row — so an abandoned onboarding never
        leaves a ghost account behind."""
        return generate_jwt(
            {"email": email, "aud": REGISTRATION_TOKEN_AUDIENCE},
            settings.REGISTRATION_TOKEN_SECRET_KEY,
            settings.REGISTRATION_TOKEN_EXPIRE_SECONDS,
        )

    @classmethod
    def verify_registration_token(cls, token: str) -> Optional[str]:
        """Decode a registration token and return its email claim, or None
        if the token is invalid, expired, or wrong-audience."""
        try:
            payload = decode_jwt(
                token,
                settings.REGISTRATION_TOKEN_SECRET_KEY,
                [REGISTRATION_TOKEN_AUDIENCE],
            )
        except PyJWTError:
            return None
        return payload.get("email")
