from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import EmailOtp
from app.otp_manager import OtpManager

EMAIL = "cooldown@example.com"


class TestOtpManagerRequestCode:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_second_request_within_cooldown_returns_none(
        self, db_session
    ) -> None:
        first = await OtpManager.request_code(db_session, EMAIL)
        assert first is not None

        second = await OtpManager.request_code(db_session, EMAIL)
        assert second is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_request_after_cooldown_issues_a_new_code(self, db_session) -> None:
        first = await OtpManager.request_code(db_session, EMAIL)
        assert first is not None

        result = await db_session.execute(
            select(EmailOtp).where(
                EmailOtp.email == EMAIL, EmailOtp.consumed_at.is_(None)
            )
        )
        otp = result.scalar_one()
        otp.creado_en = datetime.now(timezone.utc) - timedelta(
            seconds=OtpManager.RESEND_COOLDOWN_SECONDS + 1
        )
        await db_session.commit()

        second = await OtpManager.request_code(db_session, EMAIL)
        assert second is not None
        assert second != first
