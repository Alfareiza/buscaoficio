from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin import (
    NegociacionAdmin,
    PropuestaAdmin,
    SolicitudAdmin,
    _HIDE_ON_ADD_ONLY,
    _hide_fields_on_add_schema,
    _price_input,
)
from app.enums import ComplejidadCategoria, EstadoSolicitud
from app.models import (
    CategoriaServicio,
    Cliente,
    Negociacion,
    Propuesta,
    Solicitud,
    ZonaCobertura,
)
from fastadmin.models.schemas import (
    AddConfigurationFieldSchema,
    ChangeConfigurationFieldSchema,
    ModelFieldSchema,
    WidgetType,
)


class _Schema:
    def __init__(self, name: str, fields: list):
        self.name = name
        self.fields = fields


def _field(name: str) -> ModelFieldSchema:
    props = {"required": False}
    return ModelFieldSchema(
        name=name,
        list_configuration=None,
        add_configuration=AddConfigurationFieldSchema(
            index=0,
            form_widget_type=WidgetType.Input,
            form_widget_props=props,
            required=False,
        ),
        change_configuration=ChangeConfigurationFieldSchema(
            index=0,
            form_widget_type=WidgetType.Input,
            form_widget_props=dict(props),
            required=False,
        ),
    )


class TestOperacionAdminWidgets:
    def test_solicitud_fotos_and_presupuesto(self):
        admin = SolicitudAdmin(Solicitud)
        fields = {f.name: f for f in admin.get_model_fields_with_widget_types()}
        assert fields["fotos_urls"].form_widget_type == WidgetType.UploadImage
        assert (
            fields["presupuesto_aproximado"].form_widget_type == WidgetType.InputNumber
        )
        assert fields["presupuesto_aproximado"].form_widget_props["min"] == 50000
        assert fields["presupuesto_aproximado"].form_widget_props["precision"] == 0
        assert fields["creado_en"].form_widget_props["readOnly"] is True
        assert "actualizado_en" in admin.exclude
        assert fields["cliente"].form_widget_props["idField"] == "id"
        assert "estado" in _HIDE_ON_ADD_ONLY["Solicitud"]

    def test_propuesta_precio_sin_decimales(self):
        admin = PropuestaAdmin(Propuesta)
        fields = {f.name: f for f in admin.get_model_fields_with_widget_types()}
        assert fields["precio_inicial"].form_widget_props["precision"] == 0
        assert fields["solicitud"].name == "solicitud"
        assert admin.fields[0] == "solicitud"
        assert admin.fields[1] == "profesional"
        assert admin.fields[2] == "precio_inicial"
        assert admin.fields[3] == "plazo_ejecucion_dias"
        assert fields["plazo_ejecucion_dias"].form_widget_props["min"] == 1
        assert (
            fields["plazo_ejecucion_dias"].form_widget_props["style"]["width"] == "5em"
        )
        assert "actualizado_en" in admin.exclude
        assert fields["profesional"].form_widget_props["idField"] == "id"
        assert "estado" in _HIDE_ON_ADD_ONLY["Propuesta"]
        assert "resultado" in _HIDE_ON_ADD_ONLY["Negociacion"]

    def test_negociacion_hides_creado_en_on_add_via_readonly(self):
        admin = NegociacionAdmin(Negociacion)
        fields = {f.name: f for f in admin.get_model_fields_with_widget_types()}
        assert fields["creado_en"].form_widget_props["disabled"] is True
        assert fields["ronda"].form_widget_type == WidgetType.InputNumber
        assert fields["ronda"].form_widget_props["min"] == 1
        assert fields["ronda"].form_widget_props["max"] == 2

    def test_hide_on_add_keeps_change_editable(self):
        schema = _Schema(
            "Solicitud",
            [_field("motivo_cancelamiento"), _field("descripcion")],
        )
        _hide_fields_on_add_schema([schema])
        motivo = schema.fields[0]
        assert motivo.add_configuration.form_widget_props["disabled"] is True
        assert motivo.change_configuration.form_widget_props.get("disabled") is not True

    def test_solicitud_str_uses_categoria_and_creado_en(self):
        solicitud = Solicitud(
            categoria=CategoriaServicio(nombre="Pintura"),
            creado_en=datetime(2026, 9, 13, 21, 5, tzinfo=timezone.utc),
        )
        assert str(solicitud) == "Solicitud de Pintura 2026/09/13/21/05"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_get_obj_serializes_str_after_session_closes(
        self, engine, mocker, db_session, create_user
    ):
        """Change page must not 500 (UI: No permissions for model) on __str__."""
        user = await create_user(email="sol-admin@example.com")
        categoria = CategoriaServicio(
            nombre="Pintura",
            complejidad=ComplejidadCategoria.BAJA.value,
            activa_v1=False,
        )
        zona = ZonaCobertura(ciudad="Barranquilla", activa_v1=True)
        db_session.add_all([categoria, zona, Cliente(usuario_id=user.id)])
        await db_session.flush()
        solicitud = Solicitud(
            id=uuid4(),
            cliente_id=user.id,
            categoria_id=categoria.id,
            zona_id=zona.id,
            descripcion="Pintar sala",
            estado=EstadoSolicitud.PUBLICADA.value,
        )
        db_session.add(solicitud)
        await db_session.commit()

        mocker.patch.object(
            SolicitudAdmin,
            "get_sessionmaker",
            return_value=async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            ),
        )
        data = await SolicitudAdmin(Solicitud).get_obj(solicitud.id)
        assert data["__str__"] == str(solicitud)

    def test_price_input_width_fits_nine_digits(self):
        _, props = _price_input(required=False, min_value=50000)
        assert props["style"]["width"] == "11em"
        assert props["min"] == 50000
