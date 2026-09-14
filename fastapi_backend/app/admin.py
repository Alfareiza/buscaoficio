import uuid
from pathlib import Path

from fastadmin import (
    AdminApiException,
    SqlAlchemyInlineModelAdmin,
    SqlAlchemyModelAdmin,
    WidgetType,
    display,
    register,
)
from fastadmin.api.frameworks.fastapi import views as _fastadmin_views
from fastadmin.models.schemas import ModelFieldWidgetSchema
import fastadmin.api.service as _fastadmin_service
from fastapi.responses import HTMLResponse
from fastapi_users import exceptions
from fastapi_users.db import SQLAlchemyUserDatabase
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from .config import STATIC_DIR
from .database import async_session_maker
from .enums import (
    ComplejidadCategoria,
    EstadoPropuesta,
    EstadoSolicitud,
    EstadoVerificacionProfesional,
    IniciadaPor,
    ResultadoNegociacion,
    TipoDocumento,
)
from .models import (
    CategoriaServicio,
    Cliente,
    Negociacion,
    Profesional,
    Propuesta,
    Solicitud,
    SubcategoriaServicio,
    User,
    ZonaCobertura,
)
from .schemas import UserCreate
from .users import UserManager

PROFESIONAL_ENUM_FORMFIELD_OVERRIDES = {
    "documento_tipo": (
        WidgetType.Select,
        {
            "required": True,
            "options": [{"label": e.label, "value": e.value} for e in TipoDocumento],
        },
    ),
    "estado_verificacion": (
        WidgetType.Select,
        {
            "required": True,
            "options": [
                {"label": e.name, "value": e.value}
                for e in EstadoVerificacionProfesional
            ],
        },
    ),
}

CATEGORIA_ENUM_FORMFIELD_OVERRIDES = {
    "complejidad": (
        WidgetType.Select,
        {
            "required": True,
            "options": [
                {"label": e.value.capitalize(), "value": e.value}
                for e in ComplejidadCategoria
            ],
        },
    ),
}

ESTADO_VERIFICACION_BADGES = {
    EstadoVerificacionProfesional.PENDIENTE.value: "🟡 Pendiente",
    EstadoVerificacionProfesional.VERIFICADO.value: "✅ Verificado",
    EstadoVerificacionProfesional.REVISAR_MANUAL.value: "🔍 Revisar manual",
    EstadoVerificacionProfesional.RECHAZADO.value: "❌ Rechazado",
}


def _mark_immutable(fields: list[ModelFieldWidgetSchema], *names: str) -> None:
    """Hide fields from the add/edit form while leaving them in list_display.

    is_immutable only gates form rendering (fastadmin/models/helpers.py) — it
    has no effect on list columns or on get_writable_field_names(), so a
    field marked this way stays visible in the list and stays writable via
    any code that sets it programmatically (see "usuario" below).
    """
    for field in fields:
        if field.name in names:
            field.is_immutable = True


class ClienteProfesionalSharedFieldsMixin:
    """Shared fixups for admins exposing Cliente/Profesional's shared-PK usuario_id.

    fastadmin's compiled frontend hardcodes `record.id` for edit/delete
    navigation — confirmed by inspecting static/index.min.js:
    `(0,J.useCallback)(e=>{k(e.id)},[k])` for delete, and the equivalent for
    edit navigation. It's not configurable and not derived from
    list_display_links or get_model_pk_name(). Since our real PK is only
    exposed via the "usuario" relationship field (SQLAlchemy excludes FK
    columns from mapper.c, only surfacing them through relationship()), a
    literal "id" mirror field is required or delete/edit silently sends the
    string "undefined" instead of the real id.

    Also hides creado_en/actualizado_en from the add/edit form (server-set,
    never meant to be edited) while leaving them visible in list_display.
    """

    def get_model_fields_with_widget_types(
        self, with_m2m: bool | None = None
    ) -> list[ModelFieldWidgetSchema]:
        fields = super().get_model_fields_with_widget_types(with_m2m=with_m2m)
        if with_m2m:
            return fields

        _mark_immutable(fields, "creado_en", "actualizado_en")

        id_mirror = ModelFieldWidgetSchema(
            name="id",
            column_name="usuario_id",
            is_m2m=False,
            is_pk=False,
            is_immutable=True,
            form_widget_type=WidgetType.Input,
            form_widget_props={"required": False, "disabled": True, "readOnly": True},
            filter_widget_type=WidgetType.Input,
            filter_widget_props={"required": False},
        )
        return [id_mirror, *fields]


class HideDeletedUsuarioRowsMixin:
    """Keep soft-deleted usuarios' cliente/profesional rows off admin pages."""

    async def orm_get_list(
        self,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        filters: dict | None = None,
    ) -> tuple[list, int]:
        objs, _ = await super().orm_get_list(
            offset=None,
            limit=None,
            search=search,
            sort_by=sort_by,
            filters=filters,
        )
        if not objs:
            return [], 0
        usuario_ids = [obj.usuario_id for obj in objs]
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            live_ids = set(
                (
                    await session.execute(
                        select(User.id).where(
                            User.id.in_(usuario_ids),
                            User.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        live = [obj for obj in objs if obj.usuario_id in live_ids]
        total = len(live)
        if offset is not None and limit is not None:
            live = live[offset : offset + limit]
        return live, total


class ClienteInline(ClienteProfesionalSharedFieldsMixin, SqlAlchemyInlineModelAdmin):
    """Shows a User's cliente profile inline on UserAdmin's change page.

    Add/edit/delete for the underlying Cliente model still routes through
    ClienteAdmin (fastadmin resolves by model name, and the standalone
    registration wins over inlines) — this class only controls what's
    rendered inline here. usuario_id/max_num=1 keep it to the one row a
    given usuario can have.
    """

    model = Cliente
    verbose_name = "Clientes"
    verbose_name_plural = "Clientes"
    max_num = 1
    min_num = 0
    list_display = (  # noqa: RUF012
        "direccion_default",
        "repeat_customer",
        "referido_por_id",
        # "creado_en",
        # "actualizado_en",
    )


class ProfesionalInline(
    ClienteProfesionalSharedFieldsMixin, SqlAlchemyInlineModelAdmin
):
    """Shows a User's profesional profile inline on UserAdmin's change page.

    Same routing caveat as ClienteInline — saves go through ProfesionalAdmin.
    """

    model = Profesional
    verbose_name = "Profesionales"
    verbose_name_plural = "Profesionales"
    max_num = 1
    min_num = 0
    list_display = (  # noqa: RUF012
        "documento_tipo",
        "documento_numero",
        "anos_experiencia",
        "foto_perfil_url",
        "estado_verificacion",
        "whatsapp_verificado",
        "contrato_aceptado",
        "trabajos_gratis_restantes",
        "creado_en",
        "actualizado_en",
    )
    formfield_overrides = PROFESIONAL_ENUM_FORMFIELD_OVERRIDES


@register(User, sqlalchemy_sessionmaker=async_session_maker)
class UserAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Usuarios"
    verbose_name_plural = "Usuarios"
    exclude = ("hashed_password", "deleted_at")
    list_display = (  # noqa: RUF012
        "nombre_completo",
        "email",
        "whatsapp",
        "roles",
        "is_superuser",
        "is_active",
    )
    list_display_links = ("id", "email")
    # "id" dropped: a filter icon only renders for fields also in
    # list_display (fastadmin's column_index gate), and "id" isn't shown.
    list_filter = ("email", "is_superuser", "is_active")
    list_display_labels = {"roles": "Roles"}  # noqa: RUF012
    search_fields = ("email",)
    inlines = [ClienteInline, ProfesionalInline]  # noqa: RUF012
    formfield_overrides = {  # noqa: RUF012
        "username": (WidgetType.SlugInput, {"required": True}),
        "hashed_password": (WidgetType.PasswordInput, {"passwordModalForm": True}),
        "avatar_url": (
            WidgetType.UploadImage,
            {
                "required": False,
                # Disable crop image for upload field
                # "disableCropImage": True,
            },
        ),
    }

    def get_model_fields_with_widget_types(
        self, with_m2m: bool | None = None
    ) -> list[ModelFieldWidgetSchema]:
        fields = super().get_model_fields_with_widget_types(with_m2m=with_m2m)
        if not with_m2m:
            _mark_immutable(fields, "creado_en", "actualizado_en")
        return fields

    @display
    async def roles(self, obj: User) -> str:
        # Can't use list_select_related here: User.cliente/User.profesional
        # are ONETOMANY-direction relationships from SQLAlchemy's POV (the FK
        # lives on clientes/profesionales, not usuarios), and fastadmin's
        # schema builder unconditionally excludes ONETOMANY fields from the
        # exposed field set (fastadmin/models/orms/sqlalchemy.py) — so
        # list_select_related's own validation rejects it with a 422
        # ("Select related by cliente is not allowed"). A small direct lookup
        # sidesteps that entirely.
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            has_cliente = (
                await session.execute(
                    select(Cliente.usuario_id).filter_by(usuario_id=obj.id)
                )
            ).first() is not None
            has_profesional = (
                await session.execute(
                    select(Profesional.usuario_id).filter_by(usuario_id=obj.id)
                )
            ).first() is not None
        labels = []
        if has_cliente:
            labels.append("Cliente")
        if has_profesional:
            labels.append("Profesional")
        return ", ".join(labels) if labels else "—"

    @property
    def hasher(self):
        if not hasattr(self, "_hasher"):
            self._hasher = Argon2Hasher()
        return self._hasher

    async def authenticate(self, email: str, password: str) -> uuid.UUID | int | None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            qry = await session.scalars(
                select(self.model_cls).filter_by(
                    email=email,
                    is_superuser=True,
                    is_active=True,
                    deleted_at=None,
                )
            )
            if not (user := qry.first()):
                return None

            if not self.hasher.verify(password, user.hashed_password):
                return None

            return user.id

    async def change_password(self, id: uuid.UUID | int, password: str) -> None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            new_password = self.hasher.hash(password)
            query = (
                update(self.model_cls)
                .where(User.id.in_([id]))
                .values(hashed_password=new_password)
            )
            await session.execute(query)
            await session.commit()

    async def orm_get_list(
        self,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        filters: dict | None = None,
    ) -> tuple[list, int]:
        merged = dict(filters) if filters else {}
        merged[("deleted_at", "exact")] = None
        return await super().orm_get_list(offset, limit, search, sort_by, merged)

    async def orm_get_obj(self, id: uuid.UUID | int | str):
        obj = await super().orm_get_obj(id)
        if obj is None or obj.deleted_at is not None:
            return None
        return obj

    async def orm_serialize_obj_by_id(self, id: uuid.UUID | int | str) -> dict | None:
        obj = await self.orm_get_obj(id)
        if obj is None:
            return None
        return await self.serialize_obj(obj)

    async def delete_model(self, id: uuid.UUID | int | str) -> None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            user = await session.get(User, id)
            if user is None:
                raise ValueError(f"{self.model_cls.__name__} not found.")
            if user.deleted_at is not None:
                return
            await UserManager(SQLAlchemyUserDatabase(session, User)).delete(user)


class UsuarioProvisioningAdminMixin(
    ClienteProfesionalSharedFieldsMixin, HideDeletedUsuarioRowsMixin
):
    """Lets Cliente/Profesional admin forms create and edit their linked Usuario.

    On create: usuario_email/usuario_nombre_completo/usuario_password
    provision a brand-new Usuario row alongside the Cliente/Profesional, in
    one save — there is no "pick an existing usuario" picker on this form
    (the "usuario" field is hidden via is_immutable). Adding a role to an
    already-existing usuario instead happens through UserAdmin's
    ClienteInline/ProfesionalInline, which still supplies "usuario" — the
    save_model() branch below stays compatible with that path.

    On edit: the same 4 fields are pre-filled with the linked usuario's real
    current values (UsuarioProvisioningDisplayMixin in app/models.py) and,
    if changed, are written back to the usuarios table. An empty password
    field means "leave the password unchanged".
    """

    # Eager-loads "usuario" for every row on the list page too — without
    # this, usuario_nombre_completo/email/whatsapp in list_display would
    # all render blank (UsuarioProvisioningDisplayMixin's properties only
    # read the relationship when it's already loaded, to stay lazy-load-safe
    # in async SQLAlchemy). This is fastadmin's own documented mechanism
    # (models/base.py: "tell ORM to use select_related() ... on the admin
    # list page"), not something built here.
    list_select_related = ("usuario",)  # noqa: RUF012

    _USUARIO_PROVISIONING_FIELDS = (  # noqa: RUF012
        "usuario_nombre_completo",
        "usuario_password",
        "usuario_email",
        "usuario_whatsapp",
    )

    list_display_labels = {  # noqa: RUF012
        "usuario_nombre_completo": "Nombre completo",
        "usuario_password": "Password",
        "usuario_email": "Email",
        "usuario_whatsapp": "Whatsapp",
    }

    def get_model_fields_with_widget_types(
        self, with_m2m: bool | None = None
    ) -> list[ModelFieldWidgetSchema]:
        fields = super().get_model_fields_with_widget_types(with_m2m=with_m2m)
        if with_m2m:
            return fields

        # The FK relation field is named "usuario" (fastadmin names relation
        # fields by their attribute key, not the "usuario_id" column). Hide
        # it from the form entirely — creating always provisions a new
        # usuario via the fields below; is_immutable doesn't affect
        # writability, so save_model() can still set it programmatically.
        _mark_immutable(fields, "usuario")

        required_props = {"required": True, "disabled": False, "readOnly": False}
        optional_props = {"required": False, "disabled": False, "readOnly": False}
        virtual_fields = [
            ModelFieldWidgetSchema(
                name="usuario_nombre_completo",
                column_name="usuario_nombre_completo",
                is_m2m=False,
                is_pk=False,
                is_immutable=False,
                form_widget_type=WidgetType.Input,
                form_widget_props=dict(required_props),
                filter_widget_type=WidgetType.Input,
                filter_widget_props={"required": False},
            ),
            ModelFieldWidgetSchema(
                name="usuario_password",
                column_name="usuario_password",
                is_m2m=False,
                is_pk=False,
                is_immutable=False,
                # Not WidgetType.PasswordInput: that opts into fastadmin's
                # ModelAdmin.save_model wrapper, which assumes any model with
                # a password-typed field exposes its PK under
                # get_model_pk_name() as a literal dict key — true for a
                # plain "id" column, not for our relationship-backed
                # "usuario" PK. Kept optional (not required) even though
                # creating a new usuario needs one — that's enforced in
                # save_model() below — because editing must allow leaving it
                # blank to mean "keep the current password".
                form_widget_type=WidgetType.Input,
                form_widget_props=dict(optional_props),
                filter_widget_type=WidgetType.Input,
                filter_widget_props={"required": False},
            ),
            ModelFieldWidgetSchema(
                name="usuario_email",
                column_name="usuario_email",
                is_m2m=False,
                is_pk=False,
                is_immutable=False,
                form_widget_type=WidgetType.Input,
                form_widget_props=dict(required_props),
                filter_widget_type=WidgetType.Input,
                filter_widget_props={"required": False},
            ),
            ModelFieldWidgetSchema(
                name="usuario_whatsapp",
                column_name="usuario_whatsapp",
                is_m2m=False,
                is_pk=False,
                is_immutable=False,
                form_widget_type=WidgetType.Input,
                form_widget_props=dict(optional_props),
                filter_widget_type=WidgetType.Input,
                filter_widget_props={"required": False},
            ),
        ]
        return [*virtual_fields, *fields]

    async def orm_get_obj(self, id: uuid.UUID | int | str):
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            obj = await session.get(
                self.model_cls, id, options=[selectinload(self.model_cls.usuario)]
            )
            if obj is None:
                return None
            if obj.usuario is None or obj.usuario.deleted_at is not None:
                return None
            return obj

    async def orm_serialize_obj_by_id(self, id: uuid.UUID | int | str) -> dict | None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            obj = await session.get(
                self.model_cls, id, options=[selectinload(self.model_cls.usuario)]
            )
            if obj is None:
                return None
            if obj.usuario is None or obj.usuario.deleted_at is not None:
                return None
            return await self.serialize_obj(obj)

    async def save_model(
        self, id: uuid.UUID | int | str | None, payload: dict
    ) -> dict | None:
        payload = dict(payload)
        email = payload.pop("usuario_email", None)
        password = payload.pop("usuario_password", None)
        nombre_completo = payload.pop("usuario_nombre_completo", None)
        whatsapp = payload.pop("usuario_whatsapp", None)
        usuario_ref = payload.pop("usuario", None)
        payload.pop("id", None)  # mirror field, never real

        if id is not None:
            if email or password or nombre_completo or whatsapp is not None:
                await self._update_usuario(
                    id, email, password, nombre_completo, whatsapp
                )
            return await super().save_model(id, payload)

        if usuario_ref:
            # Not reachable from this admin's own form (the "usuario" field
            # is hidden), but ClienteInline/ProfesionalInline on UserAdmin
            # still submit it, auto-filled with the already-open usuario.
            payload["usuario"] = usuario_ref
            return await super().save_model(None, payload)

        if not (email and password and nombre_completo):
            raise AdminApiException(
                400,
                detail="Completa email, password y nombre_completo para crear el usuario.",
            )
        usuario_id = await self._create_usuario(
            email, password, nombre_completo, whatsapp
        )
        payload["usuario"] = usuario_id
        return await super().save_model(None, payload)

    async def _create_usuario(
        self, email: str, password: str, nombre_completo: str, whatsapp: str | None
    ) -> uuid.UUID:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            user_manager = UserManager(SQLAlchemyUserDatabase(session, User))
            try:
                user = await user_manager.create(
                    UserCreate(
                        email=email,
                        password=password,
                        nombre_completo=nombre_completo,
                        whatsapp=whatsapp,
                    ),
                    safe=True,
                )
            except exceptions.UserAlreadyExists as exc:
                raise AdminApiException(
                    400, detail="Ya existe un usuario con ese email."
                ) from exc
            except exceptions.InvalidPasswordException as exc:
                raise AdminApiException(
                    400, detail=f"Password inválido: {exc.reason}"
                ) from exc
        return user.id

    async def _update_usuario(
        self,
        usuario_id: uuid.UUID,
        email: str | None,
        password: str | None,
        nombre_completo: str | None,
        whatsapp: str | None,
    ) -> None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            user = await session.get(User, usuario_id)
            if user is None:
                return

            user_manager = UserManager(SQLAlchemyUserDatabase(session, User))

            if email and email != user.email:
                existing = await user_manager.user_db.get_by_email(email)
                if existing is not None and existing.id != usuario_id:
                    raise AdminApiException(
                        400, detail="Ya existe un usuario con ese email."
                    )
                user.email = email
            if nombre_completo:
                user.nombre_completo = nombre_completo
            if whatsapp is not None:
                user.whatsapp = whatsapp
            if password:
                try:
                    await user_manager.validate_password(password, user)
                except exceptions.InvalidPasswordException as exc:
                    raise AdminApiException(
                        400, detail=f"Password inválido: {exc.reason}"
                    ) from exc
                user.hashed_password = user_manager.password_helper.hash(password)

            await session.commit()


@register(Cliente, sqlalchemy_sessionmaker=async_session_maker)
class ClienteAdmin(UsuarioProvisioningAdminMixin, SqlAlchemyModelAdmin):
    verbose_name = "Clientes"
    verbose_name_plural = "Clientes"
    list_display = (  # noqa: RUF012
        "usuario_nombre_completo",
        "usuario_email",
        "usuario_whatsapp",
        "direccion_default",
        "repeat_customer",
        "referido_por_id",
        # "creado_en",
        # "actualizado_en",
    )
    list_display_links = ("usuario_nombre_completo",)  # noqa: RUF012
    # "creado_en" dropped: commented out of list_display above, so its
    # filter icon can't render (fastadmin's column_index gate).
    list_filter = ("repeat_customer",)  # noqa: RUF012
    search_fields = ("direccion_default",)  # noqa: RUF012


@register(Profesional, sqlalchemy_sessionmaker=async_session_maker)
class ProfesionalAdmin(UsuarioProvisioningAdminMixin, SqlAlchemyModelAdmin):
    verbose_name = "Profesional"
    verbose_name_plural = "Profesionales"
    list_display = (  # noqa: RUF012
        "usuario_nombre_completo",
        "usuario_email",
        "usuario_whatsapp",
        "whatsapp_verificado_badge",
        "documento_tipo",
        "documento_numero",
        "anos_experiencia",
        "foto_perfil_url",
        "terminos_aceptados",
        "terminos_aceptados_en",
        "score_calificacion",
        "estado_verificacion_badge",
        # "creado_en",
        # "actualizado_en",
    )
    list_display_links = ("usuario_nombre_completo",)  # noqa: RUF012
    # estado_verificacion/whatsapp_verificado dropped from list_filter: a
    # filter widget only renders for fields that are also in list_display
    # (see helpers.py's column_index gate), and the badges below replace
    # those raw columns rather than sitting alongside them.
    # contrato_aceptado/creado_en dropped too: not in list_display above
    # (contrato_aceptado was removed, creado_en is commented out), so their
    # filter icons couldn't render either.
    list_filter = (  # noqa: RUF012
        "documento_tipo",
        "terminos_aceptados",
    )
    list_display_labels = {  # noqa: RUF012
        **UsuarioProvisioningAdminMixin.list_display_labels,
        "estado_verificacion_badge": "Estado",
        "whatsapp_verificado_badge": "Whatsapp verificado",
    }
    search_fields = ("documento_numero",)  # noqa: RUF012
    formfield_overrides = PROFESIONAL_ENUM_FORMFIELD_OVERRIDES

    def get_model_fields_with_widget_types(
        self, with_m2m: bool | None = None
    ) -> list[ModelFieldWidgetSchema]:
        fields = super().get_model_fields_with_widget_types(with_m2m=with_m2m)
        if not with_m2m:
            # formfield_overrides only affects the form widget, not the
            # filter one — plain String columns default to a free-text
            # filter, which is a poor fit for an enum-like field (you'd have
            # to type "CC" exactly). Give it the same Select options here.
            for field in fields:
                if field.name == "documento_tipo":
                    field.filter_widget_type = WidgetType.Select
                    field.filter_widget_props = {
                        "required": False,
                        "options": [
                            {"label": e.label, "value": e.value} for e in TipoDocumento
                        ],
                    }
        return fields

    @display
    async def estado_verificacion_badge(self, obj: Profesional) -> str:
        return ESTADO_VERIFICACION_BADGES.get(
            obj.estado_verificacion, obj.estado_verificacion
        )

    @display
    async def whatsapp_verificado_badge(self, obj: Profesional) -> str:
        return "✅" if obj.whatsapp_verificado else "❌"


@register(CategoriaServicio, sqlalchemy_sessionmaker=async_session_maker)
class CategoriaServicioAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Categoría de servicio"
    verbose_name_plural = "Categorías de servicio"
    list_display = ("nombre", "complejidad", "activa_v1", "orden_display")  # noqa: RUF012
    list_display_links = ("nombre",)  # noqa: RUF012
    list_filter = ("complejidad", "activa_v1")  # noqa: RUF012
    search_fields = ("nombre",)  # noqa: RUF012
    formfield_overrides = CATEGORIA_ENUM_FORMFIELD_OVERRIDES


@register(SubcategoriaServicio, sqlalchemy_sessionmaker=async_session_maker)
class SubcategoriaServicioAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Subcategoría de servicio"
    verbose_name_plural = "Subcategorías de servicio"
    list_display = ("nombre", "categoria_id")  # noqa: RUF012
    list_display_links = ("nombre",)  # noqa: RUF012
    search_fields = ("nombre",)  # noqa: RUF012


@register(ZonaCobertura, sqlalchemy_sessionmaker=async_session_maker)
class ZonaCoberturaAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Zona de cobertura"
    verbose_name_plural = "Zonas de cobertura"
    list_display = ("ciudad", "localidad", "activa_v1")  # noqa: RUF012
    list_display_links = ("ciudad",)  # noqa: RUF012
    list_filter = ("activa_v1",)  # noqa: RUF012
    search_fields = ("ciudad", "localidad")  # noqa: RUF012


def _enum_select(enum_cls):
    """Select widget whose options are the enum values."""
    return (
        WidgetType.Select,
        {
            "required": True,
            "options": [{"label": e.value, "value": e.value} for e in enum_cls],
        },
    )


def _price_input(*, required: bool, min_value: int | None = None) -> tuple:
    """Ant Design InputNumber for COP amounts: integers only, optional minimum."""
    props: dict = {
        "required": required,
        "precision": 0,
        "step": 1000,
        "style": {"width": "11em"},
    }
    if min_value is not None:
        props["min"] = min_value
    return (WidgetType.InputNumber, props)


# FastAdmin's add form drops fields whose add_configuration is disabled/readOnly.
# change_configuration stays independent — patch after schema generate.
_HIDE_ON_ADD_ONLY = {
    "Solicitud": frozenset(
        {
            "estado",
            "num_profesionales_notificados",
            "primera_propuesta_en",
            "motivo_cancelamiento",
        }
    ),
    "Propuesta": frozenset({"estado", "motivo_cancelamiento", "motivo_rechazo"}),
    "Negociacion": frozenset({"resultado"}),
}


def _hide_fields_on_add_schema(schemas: list) -> list:
    """Mark fields disabled on Add so FastAdmin omits them; Change stays editable."""
    for schema in schemas:
        names = _HIDE_ON_ADD_ONLY.get(getattr(schema, "name", ""))
        if not names:
            continue
        for field in schema.fields:
            add = field.add_configuration
            if add is None or field.name not in names:
                continue
            add.form_widget_props = {
                **(add.form_widget_props or {}),
                "disabled": True,
                "readOnly": True,
            }
    return schemas


@register(Solicitud, sqlalchemy_sessionmaker=async_session_maker)
class SolicitudAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Solicitud"
    verbose_name_plural = "Solicitudes"
    fields = (  # noqa: RUF012
        "cliente",
        "categoria",
        "zona",
        "es_urgente",
        "presupuesto_aproximado",
        "descripcion",
        "fotos_urls",
        "estado",
        "num_profesionales_notificados",
        "primera_propuesta_en",
        "motivo_cancelamiento",
        "creado_en",
    )
    list_display = ("id", "cliente", "categoria", "zona", "estado", "es_urgente")  # noqa: RUF012
    list_display_links = ("id",)  # noqa: RUF012
    list_filter = ("estado", "es_urgente")  # noqa: RUF012
    search_fields = ("descripcion",)  # noqa: RUF012
    exclude = ("actualizado_en",)
    readonly_fields = ("creado_en",)  # noqa: RUF012
    list_display_labels = {  # noqa: RUF012
        "presupuesto_aproximado": "Presupuesto estimado",
        "fotos_urls": "Fotos",
        "es_urgente": "Es urgente",
        "num_profesionales_notificados": "Num de profesionales notificados",
        "primera_propuesta_en": "Primera propuesta",
        "motivo_cancelamiento": "Motivo cancelamiento",
        "creado_en": "Creado en",
        "cliente": "Cliente",
        "categoria": "Categoría",
        "zona": "Zona",
    }
    formfield_overrides = {
        "estado": _enum_select(EstadoSolicitud),
        "presupuesto_aproximado": _price_input(required=False, min_value=50000),
        "fotos_urls": (
            WidgetType.UploadImage,
            {"required": False, "disableCropImage": True},
        ),
        "descripcion": (WidgetType.TextArea, {"required": True}),
        # Cliente PK is usuario_id; list rows expose it as `id` (see mixin).
        "cliente": (
            WidgetType.AsyncSelect,
            {
                "required": True,
                "parentModel": "Cliente",
                "idField": "id",
                "labelFields": ["__str__", "id"],
            },
        ),
    }

    async def orm_get_list(
        self, offset=None, limit=None, search=None, sort_by=None, filters=None
    ):
        """List page: one extra IN() query loads cliente.usuario / categoria / zona.

        FastAdmin serializes after the list session closes. Without this
        batch, ``str(obj.cliente)`` would lazy-load ``usuario`` per row (N+1)
        or fail detached. Not N+1: two queries total, not one per row.
        """
        objs, total = await super().orm_get_list(
            offset=offset, limit=limit, search=search, sort_by=sort_by, filters=filters
        )
        if not objs:
            return objs, total
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            loaded = (
                await session.scalars(
                    select(Solicitud)
                    .where(Solicitud.id.in_([obj.id for obj in objs]))
                    .options(
                        selectinload(Solicitud.cliente).selectinload(Cliente.usuario),
                        selectinload(Solicitud.categoria),
                        selectinload(Solicitud.zona),
                    )
                )
            ).all()
            by_id = {row.id: row for row in loaded}
            return [by_id[obj.id] for obj in objs], total

    async def orm_get_obj(self, id):
        """Change page: load ``categoria`` before the session closes.

        FastAdmin then calls ``Solicitud.__str__`` on a detached instance. A
        500 there is shown as "No permissions for model".
        """
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            return await session.get(
                Solicitud,
                id,
                options=(
                    selectinload(Solicitud.cliente).selectinload(Cliente.usuario),
                    selectinload(Solicitud.categoria),
                    selectinload(Solicitud.zona),
                ),
            )

    async def serialize_obj_attributes(
        self, obj, attributes_to_serizalize, list_view: bool = False
    ) -> dict:
        """List columns use each related object's ``__str__``; fotos stay URL list."""
        data = await super().serialize_obj_attributes(
            obj, attributes_to_serizalize, list_view=list_view
        )
        if list_view:
            data["cliente"] = str(obj.cliente)
            data["categoria"] = str(obj.categoria)
            data["zona"] = str(obj.zona)
        urls = data.get("fotos_urls")
        if not isinstance(urls, list):
            return data
        first = urls[0] if urls else None
        if list_view:
            data["fotos_urls"] = ", ".join(str(u) for u in urls) if urls else None
            return data
        data["fotos_urls"] = first
        if first:
            data["fotos_urls__url"] = await self.get_file_url("fotos_urls", first, obj)
        return data

    async def save_model(self, id, payload: dict):
        """UploadImage submits one URL string; the column stores a JSON list."""
        raw = payload.get("fotos_urls")
        if isinstance(raw, str) and raw:
            payload["fotos_urls"] = [raw]
        elif raw in ("", None):
            payload["fotos_urls"] = None
        return await super().save_model(id, payload)

    async def upload_file(
        self, field_name: str, file_name: str, file_content: bytes, obj=None
    ) -> str:
        """Write the image under ``/static`` so FastAdmin can preview without S3."""
        dest = STATIC_DIR / "admin-uploads" / "solicitudes"
        dest.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}_{Path(file_name).name}"
        (dest / stored).write_bytes(file_content)
        return f"/static/admin-uploads/solicitudes/{stored}"


@register(Propuesta, sqlalchemy_sessionmaker=async_session_maker)
class PropuestaAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Propuesta"
    verbose_name_plural = "Propuestas"
    fields = (  # noqa: RUF012
        "solicitud",
        "profesional",
        "precio_inicial",
        "plazo_ejecucion_dias",
        "descripcion_enfoque",
        "estado",
        "motivo_cancelamiento",
        "motivo_rechazo",
        "creado_en",
    )
    list_display = ("id", "solicitud", "profesional", "estado")  # noqa: RUF012
    list_display_links = ("id",)  # noqa: RUF012
    list_filter = ("estado",)  # noqa: RUF012
    exclude = ("actualizado_en",)
    readonly_fields = ("creado_en",)  # noqa: RUF012
    list_display_labels = {  # noqa: RUF012
        "precio_inicial": "Precio inicial",
        "plazo_ejecucion_dias": "Plazo ejecución días",
        "motivo_cancelamiento": "Motivo cancelamiento",
        "motivo_rechazo": "Motivo rechazo",
        "creado_en": "Creado en",
        "solicitud": "Solicitud",
        "profesional": "Profesional",
    }
    formfield_overrides = {
        "estado": _enum_select(EstadoPropuesta),
        "precio_inicial": _price_input(required=True),
        "profesional": (
            WidgetType.AsyncSelect,
            {
                "required": True,
                "parentModel": "Profesional",
                "idField": "id",
                "labelFields": ["__str__", "id"],
            },
        ),
        "plazo_ejecucion_dias": (
            WidgetType.InputNumber,
            {
                "required": False,
                "min": 1,
                "max": 99,
                "precision": 0,
                "style": {"width": "5em"},
            },
        ),
    }

    async def orm_get_list(
        self, offset=None, limit=None, search=None, sort_by=None, filters=None
    ):
        """Same batch as SolicitudAdmin: ``solicitud.categoria`` and
        ``profesional.usuario`` for ``__str__``, one IN() query, not N+1.
        """
        objs, total = await super().orm_get_list(
            offset=offset, limit=limit, search=search, sort_by=sort_by, filters=filters
        )
        if not objs:
            return objs, total
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            loaded = (
                await session.scalars(
                    select(Propuesta)
                    .where(Propuesta.id.in_([obj.id for obj in objs]))
                    .options(
                        selectinload(Propuesta.solicitud).selectinload(
                            Solicitud.categoria
                        ),
                        selectinload(Propuesta.profesional).selectinload(
                            Profesional.usuario
                        ),
                    )
                )
            ).all()
            by_id = {row.id: row for row in loaded}
            return [by_id[obj.id] for obj in objs], total

    async def serialize_obj_attributes(
        self, obj, attributes_to_serizalize, list_view: bool = False
    ) -> dict:
        """List columns use ``Solicitud.__str__`` and ``Profesional.__str__``."""
        data = await super().serialize_obj_attributes(
            obj, attributes_to_serizalize, list_view=list_view
        )
        if list_view:
            data["solicitud"] = str(obj.solicitud)
            data["profesional"] = str(obj.profesional)
        return data


@register(Negociacion, sqlalchemy_sessionmaker=async_session_maker)
class NegociacionAdmin(SqlAlchemyModelAdmin):
    verbose_name = "Negociación"
    verbose_name_plural = "Negociaciones"
    fields = (  # noqa: RUF012
        "propuesta",
        "ronda",
        "iniciada_por",
        "precio_propuesto",
        "resultado",
        "creado_en",
    )
    list_display = ("id", "propuesta", "ronda", "iniciada_por", "resultado")  # noqa: RUF012
    list_display_links = ("id",)  # noqa: RUF012
    list_select_related = ("propuesta",)  # noqa: RUF012
    list_filter = ("resultado", "iniciada_por")  # noqa: RUF012
    exclude = ("actualizado_en",)
    readonly_fields = ("creado_en",)  # noqa: RUF012
    list_display_labels = {"creado_en": "Creado en"}  # noqa: RUF012
    formfield_overrides = {
        "iniciada_por": _enum_select(IniciadaPor),
        "resultado": _enum_select(ResultadoNegociacion),
        "precio_propuesto": _price_input(required=True, min_value=1),
        # SmallInteger is not in FastAdmin's Integer|Float|Decimal match → Input (str).
        "ronda": (
            WidgetType.InputNumber,
            {
                "required": True,
                "min": 1,
                "max": 2,
                "precision": 0,
                "style": {"width": "5em"},
            },
        ),
    }

    async def serialize_obj_attributes(
        self, obj, attributes_to_serizalize, list_view: bool = False
    ) -> dict:
        """List shows ``Propuesta.__str__``; ``list_select_related`` loads it once."""
        data = await super().serialize_obj_attributes(
            obj, attributes_to_serizalize, list_view=list_view
        )
        if list_view:
            data["propuesta"] = str(obj.propuesta)
        return data


_generate_models_schema = _fastadmin_service.generate_models_schema


async def _generate_models_schema_hide_on_add(*args, **kwargs):
    """Apply ``_HIDE_ON_ADD_ONLY`` after FastAdmin builds the form schema."""
    schemas = await _generate_models_schema(*args, **kwargs)
    return _hide_fields_on_add_schema(schemas)


_fastadmin_service.generate_models_schema = _generate_models_schema_hide_on_add

_admin_index = _fastadmin_views.index


def _admin_index_with_operacion_css():
    """Inject the Operación form CSS (Precio + Plazo on one row)."""
    html = _admin_index()
    body = html.body.decode() if isinstance(html, HTMLResponse) else str(html)
    link = '<link rel="stylesheet" href="/static/css/fastadmin-operacion.css">'
    return HTMLResponse(body.replace("</head>", f"{link}</head>", 1))


_fastadmin_views.index = _admin_index_with_operacion_css
