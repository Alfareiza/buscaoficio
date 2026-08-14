import pytest
from fastapi import status
from fastapi_users.router import ErrorCode
from sqlalchemy import select
from app.models import Cliente, Profesional, User


class TestPasswordValidation:
    @pytest.mark.parametrize(
        "email, password, expected_status, expected_detail",
        [
            (
                "test@example.com",
                "short",
                status.HTTP_400_BAD_REQUEST,
                {
                    "detail": {
                        "code": ErrorCode.REGISTER_INVALID_PASSWORD.value,
                        "reason": ["Password should be at least 8 characters."],
                    }
                },
            ),
            (
                "test@example.com",
                "test@example.com",
                status.HTTP_400_BAD_REQUEST,
                {
                    "detail": {
                        "code": ErrorCode.REGISTER_INVALID_PASSWORD.value,
                        "reason": ["Password should not contain e-mail."],
                    }
                },
            ),
            (
                "test@example.com",
                "lowercasepassword",
                status.HTTP_400_BAD_REQUEST,
                {
                    "detail": {
                        "code": ErrorCode.REGISTER_INVALID_PASSWORD.value,
                        "reason": [
                            "Password should contain at least one uppercase letter."
                        ],
                    }
                },
            ),
            (
                "test@example.com",
                "Nosppecialchar1",
                status.HTTP_400_BAD_REQUEST,
                {
                    "detail": {
                        "code": ErrorCode.REGISTER_INVALID_PASSWORD.value,
                        "reason": [
                            "Password should contain at least one special character."
                        ],
                    }
                },
            ),
            (
                "test@example.com",
                "shorttest",
                status.HTTP_400_BAD_REQUEST,
                {
                    "detail": {
                        "code": ErrorCode.REGISTER_INVALID_PASSWORD.value,
                        "reason": [
                            "Password should be at least 8 characters.",
                            "Password should contain at least one uppercase letter.",
                            "Password should contain at least one special character.",
                        ],
                    }
                },
            ),
        ],
    )
    @pytest.mark.asyncio(loop_scope="function")
    async def test_password_validation(
        self, test_client, email, password, expected_status, expected_detail
    ):
        """Test user registration with password validation."""
        json = {"email": email, "password": password, "nombre_completo": "Test User"}
        response = await test_client.post("/api/v1/auth/register", json=json)

        assert response.status_code == expected_status

    @pytest.mark.asyncio(loop_scope="function")
    async def test_register_user_with_valid_password(self, test_client, db_session):
        """Test user registration with success"""
        json = {
            "email": "user@1.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "User One",
        }
        response = await test_client.post("/api/v1/auth/register", json=json)

        row = await db_session.execute(select(User))

        user = row.scalars().first()

        assert response.status_code == status.HTTP_201_CREATED
        assert user is not None
        assert user.email == "user@1.com"


class TestRegisterCliente:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_cliente_in_one_request(
        self, test_client, db_session
    ):
        """A single POST creates both the usuario and cliente rows."""
        json = {
            "email": "cliente@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Cliente Uno",
            "direccion_default": "Calle 1 # 2-3",
        }
        response = await test_client.post("/api/v1/auth/register/cliente", json=json)

        assert response.status_code == status.HTTP_201_CREATED
        user = (
            await db_session.execute(
                select(User).filter_by(email="cliente@example.com")
            )
        ).scalar_one()
        cliente = (
            await db_session.execute(select(Cliente).filter_by(usuario_id=user.id))
        ).scalar_one()
        assert cliente.direccion_default == "Calle 1 # 2-3"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_duplicate_email(self, test_client, create_user):
        await create_user(email="dupe@example.com")
        json = {
            "email": "dupe@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Someone",
        }
        response = await test_client.post("/api/v1/auth/register/cliente", json=json)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_unknown_referido_por_id(self, test_client):
        json = {
            "email": "cliente2@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Cliente Dos",
            "referido_por_id": "00000000-0000-0000-0000-000000000000",
        }
        response = await test_client.post("/api/v1/auth/register/cliente", json=json)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRegisterProfesional:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_profesional_in_one_request(
        self, test_client, db_session
    ):
        """A single POST creates both the usuario and profesional rows."""
        json = {
            "email": "profesional@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Profesional Uno",
            "documento_tipo": "CC",
            "documento_numero": "123456789",
        }
        response = await test_client.post(
            "/api/v1/auth/register/profesional", json=json
        )

        assert response.status_code == status.HTTP_201_CREATED
        user = (
            await db_session.execute(
                select(User).filter_by(email="profesional@example.com")
            )
        ).scalar_one()
        profesional = (
            await db_session.execute(select(Profesional).filter_by(usuario_id=user.id))
        ).scalar_one()
        assert profesional.documento_numero == "123456789"
        assert profesional.estado_verificacion == "pendiente"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_duplicate_documento_numero(
        self, test_client, db_session, create_user
    ):
        existing_user = await create_user(email="existing.pro@example.com")
        db_session.add(
            Profesional(
                usuario_id=existing_user.id, documento_tipo="CC", documento_numero="999"
            )
        )
        await db_session.commit()

        json = {
            "email": "another@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Otro",
            "documento_tipo": "CC",
            "documento_numero": "999",
        }
        response = await test_client.post(
            "/api/v1/auth/register/profesional", json=json
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_duplicate_email(self, test_client, create_user):
        await create_user(email="dupe2@example.com")
        json = {
            "email": "dupe2@example.com",
            "password": "Sppecialchar1#",
            "nombre_completo": "Someone",
            "documento_tipo": "CC",
            "documento_numero": "111",
        }
        response = await test_client.post(
            "/api/v1/auth/register/profesional", json=json
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
