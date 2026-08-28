"""Tests for ``ClienteAdmin``/``ProfesionalAdmin`` inline usuario provisioning."""

import pytest
from fastadmin import AdminApiException
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin import ClienteAdmin, ProfesionalAdmin, UserAdmin
from app.enums import EstadoVerificacionProfesional, TipoDocumento
from app.models import Cliente, Profesional, User
from app.users import UserManager


@pytest.fixture
def cliente_admin(engine, mocker) -> ClienteAdmin:
    test_sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    mocker.patch.object(
        ClienteAdmin, "get_sessionmaker", return_value=test_sessionmaker
    )
    return ClienteAdmin(Cliente)


@pytest.fixture
def profesional_admin(engine, mocker) -> ProfesionalAdmin:
    test_sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    mocker.patch.object(
        ProfesionalAdmin, "get_sessionmaker", return_value=test_sessionmaker
    )
    return ProfesionalAdmin(Profesional)


class TestClienteAdminSaveModelCreate:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_cliente_when_no_usuario_picked(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession
    ):
        payload = {
            "usuario": None,
            "usuario_email": "nuevo.cliente@example.com",
            "usuario_password": "SecurePass123#",
            "usuario_nombre_completo": "Nuevo Cliente",
            "usuario_whatsapp": "+573001112233",
            "direccion_default": "Calle 1 # 2-3",
            "repeat_customer": False,
        }

        result = await cliente_admin.save_model(None, payload)

        assert result is not None
        user_row = (
            await db_session.execute(
                select(User).filter_by(email="nuevo.cliente@example.com")
            )
        ).scalar_one()
        assert user_row.nombre_completo == "Nuevo Cliente"

        cliente_row = (
            await db_session.execute(select(Cliente).filter_by(usuario_id=user_row.id))
        ).scalar_one()
        assert cliente_row.direccion_default == "Calle 1 # 2-3"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_uses_existing_usuario_without_creating_duplicate(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        user = await create_user(email="existing@example.com")
        payload = {
            "usuario": str(user.id),
            "usuario_email": None,
            "usuario_password": None,
            "usuario_nombre_completo": None,
            "usuario_whatsapp": None,
            "direccion_default": "Existing address",
            "repeat_customer": True,
        }

        await cliente_admin.save_model(None, payload)

        users = (
            (
                await db_session.execute(
                    select(User).filter_by(email="existing@example.com")
                )
            )
            .scalars()
            .all()
        )
        assert len(users) == 1

        cliente_row = (
            await db_session.execute(select(Cliente).filter_by(usuario_id=user.id))
        ).scalar_one()
        assert cliente_row.repeat_customer is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_raises_when_neither_usuario_nor_new_user_fields_given(
        self, cliente_admin: ClienteAdmin
    ):
        payload = {
            "usuario": None,
            "usuario_email": None,
            "usuario_password": None,
            "usuario_nombre_completo": None,
            "usuario_whatsapp": None,
            "direccion_default": None,
            "repeat_customer": False,
        }

        with pytest.raises(AdminApiException):
            await cliente_admin.save_model(None, payload)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_raises_on_duplicate_email(
        self, cliente_admin: ClienteAdmin, create_user
    ):
        await create_user(email="dupe@example.com")
        payload = {
            "usuario": None,
            "usuario_email": "dupe@example.com",
            "usuario_password": "SecurePass123#",
            "usuario_nombre_completo": "Someone Else",
            "usuario_whatsapp": None,
            "direccion_default": None,
            "repeat_customer": False,
        }

        with pytest.raises(AdminApiException):
            await cliente_admin.save_model(None, payload)


class TestClienteAdminSaveModelEdit:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_updates_linked_usuario_fields(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        user = await create_user(
            email="cliente.edit@example.com", nombre_completo="Old Name"
        )
        cliente = Cliente(usuario_id=user.id, direccion_default="Old address")
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        payload = {
            "direccion_default": "New address",
            "repeat_customer": True,
            "usuario_email": "updated@example.com",
            "usuario_password": None,
            "usuario_nombre_completo": "New Name",
            "usuario_whatsapp": "+573000000000",
        }

        await cliente_admin.save_model(cliente.usuario_id, payload)

        await db_session.refresh(user)
        await db_session.refresh(cliente)
        assert user.email == "updated@example.com"
        assert user.nombre_completo == "New Name"
        assert user.whatsapp == "+573000000000"
        assert cliente.direccion_default == "New address"
        assert cliente.repeat_customer is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_blank_password_leaves_it_unchanged(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        user = await create_user(
            email="keep.pass@example.com", password="OriginalPass123#"
        )
        original_hash = user.hashed_password
        cliente = Cliente(usuario_id=user.id)
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        payload = {
            "direccion_default": None,
            "repeat_customer": False,
            "usuario_email": None,
            "usuario_password": None,
            "usuario_nombre_completo": None,
            "usuario_whatsapp": None,
        }

        await cliente_admin.save_model(cliente.usuario_id, payload)

        await db_session.refresh(user)
        assert user.hashed_password == original_hash

    @pytest.mark.asyncio(loop_scope="function")
    async def test_new_password_changes_hash(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        user = await create_user(
            email="change.pass@example.com", password="OriginalPass123#"
        )
        original_hash = user.hashed_password
        cliente = Cliente(usuario_id=user.id)
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        payload = {
            "direccion_default": None,
            "repeat_customer": False,
            "usuario_email": None,
            "usuario_password": "BrandNewPass456#",
            "usuario_nombre_completo": None,
            "usuario_whatsapp": None,
        }

        await cliente_admin.save_model(cliente.usuario_id, payload)

        await db_session.refresh(user)
        assert user.hashed_password != original_hash

    @pytest.mark.asyncio(loop_scope="function")
    async def test_raises_on_duplicate_email_when_editing(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        await create_user(email="taken@example.com")
        user = await create_user(email="cliente3@example.com")
        cliente = Cliente(usuario_id=user.id)
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        payload = {
            "direccion_default": None,
            "repeat_customer": False,
            "usuario_email": "taken@example.com",
            "usuario_password": None,
            "usuario_nombre_completo": None,
            "usuario_whatsapp": None,
        }

        with pytest.raises(AdminApiException):
            await cliente_admin.save_model(cliente.usuario_id, payload)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_get_obj_prefills_real_usuario_values(
        self, cliente_admin: ClienteAdmin, db_session: AsyncSession, create_user
    ):
        user = await create_user(
            email="prefill@example.com", nombre_completo="Prefill Name"
        )
        cliente = Cliente(usuario_id=user.id, direccion_default="Some address")
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        obj = await cliente_admin.get_obj(cliente.usuario_id)

        assert obj is not None
        assert obj["usuario_email"] == "prefill@example.com"
        assert obj["usuario_nombre_completo"] == "Prefill Name"
        assert obj["usuario_password"] is None
        assert obj["id"] == cliente.usuario_id


class TestSharedFieldsSchema:
    """Schema-level checks for the creado_en/actualizado_en/usuario/id fixups."""

    def test_cliente_admin_hides_creado_en_usuario_shows_id_mirror(
        self, cliente_admin: ClienteAdmin
    ):
        fields = {f.name: f for f in cliente_admin.get_model_fields_with_widget_types()}

        assert fields["creado_en"].is_immutable is True
        assert fields["actualizado_en"].is_immutable is True
        assert fields["usuario"].is_immutable is True
        assert fields["id"].column_name == "usuario_id"
        assert fields["id"].is_immutable is True
        assert fields["usuario_email"].form_widget_props["required"] is True
        assert fields["usuario_nombre_completo"].form_widget_props["required"] is True
        assert fields["usuario_password"].form_widget_props["required"] is False

    def test_profesional_admin_hides_creado_en_usuario_shows_id_mirror(
        self, profesional_admin: ProfesionalAdmin
    ):
        fields = {
            f.name: f for f in profesional_admin.get_model_fields_with_widget_types()
        }

        assert fields["creado_en"].is_immutable is True
        assert fields["actualizado_en"].is_immutable is True
        assert fields["usuario"].is_immutable is True
        assert fields["id"].column_name == "usuario_id"

    def test_user_admin_hides_creado_en(self):
        fields = {
            f.name: f for f in UserAdmin(User).get_model_fields_with_widget_types()
        }

        assert fields["creado_en"].is_immutable is True
        assert fields["actualizado_en"].is_immutable is True


class TestProfesionalAdminSaveModelCreate:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_creates_usuario_and_profesional_when_no_usuario_picked(
        self, profesional_admin: ProfesionalAdmin, db_session: AsyncSession
    ):
        payload = {
            "usuario": None,
            "usuario_email": "nuevo.profesional@example.com",
            "usuario_password": "SecurePass123#",
            "usuario_nombre_completo": "Nuevo Profesional",
            "usuario_whatsapp": None,
            "documento_tipo": TipoDocumento.CC.value,
            "documento_numero": "123456789",
            "anos_experiencia": 5,
            "foto_perfil_url": None,
        }

        await profesional_admin.save_model(None, payload)

        user_row = (
            await db_session.execute(
                select(User).filter_by(email="nuevo.profesional@example.com")
            )
        ).scalar_one()
        profesional_row = (
            await db_session.execute(
                select(Profesional).filter_by(usuario_id=user_row.id)
            )
        ).scalar_one()
        assert profesional_row.documento_numero == "123456789"
        assert (
            profesional_row.estado_verificacion
            == EstadoVerificacionProfesional.PENDIENTE.value
        )


class TestClienteAdminHidesDeletedUsuario:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_list_omits_cliente_of_deleted_usuario(
        self,
        cliente_admin: ClienteAdmin,
        db_session: AsyncSession,
        create_user,
    ):
        user = await create_user(email="deleted.cliente@example.com")
        db_session.add(Cliente(usuario_id=user.id, direccion_default="Calle 1"))
        await db_session.commit()

        await UserManager(SQLAlchemyUserDatabase(db_session, User)).delete(user)

        objs, total = await cliente_admin.orm_get_list()

        assert total == 0
        assert objs == []

    @pytest.mark.asyncio(loop_scope="function")
    async def test_get_obj_returns_none_for_deleted_usuario(
        self,
        cliente_admin: ClienteAdmin,
        db_session: AsyncSession,
        create_user,
    ):
        user = await create_user(email="hidden.cliente@example.com")
        db_session.add(Cliente(usuario_id=user.id))
        await db_session.commit()

        await UserManager(SQLAlchemyUserDatabase(db_session, User)).delete(user)

        assert await cliente_admin.orm_get_obj(user.id) is None
