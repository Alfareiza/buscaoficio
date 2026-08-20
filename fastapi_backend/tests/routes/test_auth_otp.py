"""Integration tests for the passwordless (email OTP) auth flow."""

from collections.abc import Awaitable, Callable

import pytest
from fastapi import status
from sqlalchemy import select

from app.models import Cliente, Profesional, User
from app.otp_manager import OtpManager

NEW_EMAIL = "new-user@example.com"


@pytest.fixture(autouse=True)
def mock_send_otp_email(mocker):
    """Never hit real SMTP in tests; capture the code that would've been sent."""
    return mocker.patch("app.routes.auth.send_otp_code_email", mocker.AsyncMock())


async def _request_and_capture_code(
    test_client, mock_send_otp_email, email: str
) -> str:
    response = await test_client.post("/api/v1/auth/otp/request", json={"email": email})
    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_send_otp_email.assert_awaited_once()
    return mock_send_otp_email.call_args[0][1]


class TestOtpRequest:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_request_always_returns_202(self, test_client) -> None:
        response = await test_client.post(
            "/api/v1/auth/otp/request", json={"email": "anything@example.com"}
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

    @pytest.mark.asyncio(loop_scope="function")
    async def test_request_sends_a_code(self, test_client, mock_send_otp_email) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )
        assert len(code) == OtpManager.CODE_LENGTH
        assert code.isdigit()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_resend_within_cooldown_still_returns_202_but_does_not_email(
        self, test_client, mock_send_otp_email
    ) -> None:
        await _request_and_capture_code(test_client, mock_send_otp_email, NEW_EMAIL)
        mock_send_otp_email.reset_mock()

        response = await test_client.post(
            "/api/v1/auth/otp/request", json={"email": NEW_EMAIL}
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        mock_send_otp_email.assert_not_awaited()


class TestOtpVerifyNewEmail:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_verify_unknown_email_returns_registration_token(
        self, test_client, mock_send_otp_email
    ) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )

        response = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "new_user"
        assert (
            isinstance(body["registration_token"], str) and body["registration_token"]
        )

    @pytest.mark.asyncio(loop_scope="function")
    async def test_verify_wrong_code_returns_400(
        self, test_client, mock_send_otp_email
    ) -> None:
        await _request_and_capture_code(test_client, mock_send_otp_email, NEW_EMAIL)

        response = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": "000000"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio(loop_scope="function")
    async def test_verify_code_cannot_be_reused(
        self, test_client, mock_send_otp_email
    ) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )

        first = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        assert first.status_code == status.HTTP_200_OK

        second = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        assert second.status_code == status.HTTP_400_BAD_REQUEST


class TestOtpVerifyExistingUser:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_verify_existing_user_logs_in(
        self,
        test_client,
        mock_send_otp_email,
        create_user: Callable[..., Awaitable[User]],
        db_session,
    ) -> None:
        user = await create_user(email="existing@example.com")
        db_session.add(Cliente(usuario_id=user.id))
        await db_session.commit()

        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, user.email
        )

        response = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": user.email, "code": code}
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "existing_user"
        assert body["has_role"] is True
        assert "access_token" in body
        assert "refreshToken" in response.cookies
        assert "fingerprintToken" in response.cookies

    @pytest.mark.asyncio(loop_scope="function")
    async def test_verify_existing_user_without_role_flags_has_role_false(
        self,
        test_client,
        mock_send_otp_email,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        user = await create_user(email="roleless@example.com")

        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, user.email
        )

        response = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": user.email, "code": code}
        )

        assert response.json()["has_role"] is False


class TestRegisterClienteOtp:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_cliente_then_logs_in(
        self, test_client, mock_send_otp_email, db_session
    ) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )
        verify = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        registration_token = verify.json()["registration_token"]

        response = await test_client.post(
            "/api/v1/auth/register/cliente/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Nueva Clienta",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "existing_user"
        assert body["has_role"] is True
        assert "access_token" in body

        result = await db_session.execute(select(User).where(User.email == NEW_EMAIL))
        user = result.scalar_one()
        assert user.nombre_completo == "Nueva Clienta"
        assert user.is_verified is True

        cliente = await db_session.execute(
            select(Cliente).where(Cliente.usuario_id == user.id)
        )
        assert cliente.scalar_one_or_none() is not None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_registration_token_returns_400(self, test_client) -> None:
        response = await test_client.post(
            "/api/v1/auth/register/cliente/otp",
            json={
                "registration_token": "not-a-real-token",
                "nombre_completo": "Nueva Clienta",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_unknown_referido_por_id(
        self, test_client, mock_send_otp_email
    ) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )
        verify = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        registration_token = verify.json()["registration_token"]

        response = await test_client.post(
            "/api/v1/auth/register/cliente/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Nueva Clienta",
                "referido_por_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRegisterProfesionalOtp:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_profesional_then_logs_in(
        self, test_client, mock_send_otp_email, db_session
    ) -> None:
        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )
        verify = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        registration_token = verify.json()["registration_token"]

        response = await test_client.post(
            "/api/v1/auth/register/profesional/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Nuevo Profesional",
                "documento_tipo": "CC",
                "documento_numero": "123456789",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["has_role"] is True

        result = await db_session.execute(select(User).where(User.email == NEW_EMAIL))
        user = result.scalar_one()

        profesional = await db_session.execute(
            select(Profesional).where(Profesional.usuario_id == user.id)
        )
        row = profesional.scalar_one_or_none()
        assert row is not None
        assert row.documento_numero == "123456789"
        assert row.estado_verificacion == "pendiente"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_duplicate_documento_numero_returns_409(
        self,
        test_client,
        mock_send_otp_email,
        db_session,
        create_user: Callable[..., Awaitable[User]],
    ) -> None:
        existing_user = await create_user(email="taken-doc@example.com")
        db_session.add(
            Profesional(
                usuario_id=existing_user.id,
                documento_tipo="CC",
                documento_numero="999999999",
            )
        )
        await db_session.commit()

        code = await _request_and_capture_code(
            test_client, mock_send_otp_email, NEW_EMAIL
        )
        verify = await test_client.post(
            "/api/v1/auth/otp/verify", json={"email": NEW_EMAIL, "code": code}
        )
        registration_token = verify.json()["registration_token"]

        response = await test_client.post(
            "/api/v1/auth/register/profesional/otp",
            json={
                "registration_token": registration_token,
                "nombre_completo": "Nuevo Profesional",
                "documento_tipo": "CC",
                "documento_numero": "999999999",
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
