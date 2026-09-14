from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlalchemy import select

from app.enums import ComplejidadCategoria, EstadoPropuesta, EstadoSolicitud
from app.models import (
    CategoriaServicio,
    Cliente,
    Profesional,
    ProfesionalCategoria,
    ProfesionalZona,
    Propuesta,
    Solicitud,
    User,
    ZonaCobertura,
)
from tests.conftest import issue_auth_headers

CAT_ID = UUID("11111111-1111-4111-8111-111111110001")
ZONA_ID = UUID("22222222-2222-4222-8222-222222222001")
OTHER_CAT_ID = UUID("11111111-1111-4111-8111-111111110099")


async def _seed_catalog(db_session) -> None:
    db_session.add_all(
        [
            CategoriaServicio(
                id=CAT_ID,
                nombre="Pintura",
                complejidad=ComplejidadCategoria.BAJA.value,
                activa_v1=False,
            ),
            CategoriaServicio(
                id=OTHER_CAT_ID,
                nombre="Otra",
                complejidad=ComplejidadCategoria.MEDIA.value,
                activa_v1=False,
            ),
            ZonaCobertura(id=ZONA_ID, ciudad="Barranquilla", activa_v1=True),
        ]
    )
    await db_session.commit()


async def _cliente_auth(db_session, create_user, email="cli@example.com"):
    user = await create_user(email=email, nombre_completo="Ana Cliente")
    db_session.add(Cliente(usuario_id=user.id))
    await db_session.commit()
    return user, await issue_auth_headers(user)


async def _profesional_auth(db_session, create_user, email="pro@example.com"):
    user = await create_user(email=email, nombre_completo="Pedro Pro")
    db_session.add(
        Profesional(
            usuario_id=user.id, documento_tipo="CC", documento_numero=email[:10]
        )
    )
    db_session.add(ProfesionalCategoria(usuario_id=user.id, categoria_id=CAT_ID))
    db_session.add(ProfesionalZona(usuario_id=user.id, zona_id=ZONA_ID))
    await db_session.commit()
    return user, await issue_auth_headers(user)


class TestSolicitudes:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_create_and_list_as_cliente(
        self, test_client, db_session, create_user: Callable[..., Awaitable[User]]
    ):
        await _seed_catalog(db_session)
        _, headers = await _cliente_auth(db_session, create_user)

        response = await test_client.post(
            "/api/v1/solicitudes/",
            headers=headers,
            json={
                "categoria_id": str(CAT_ID),
                "zona_id": str(ZONA_ID),
                "descripcion": "Filtración en el techo",
                "fotos_urls": ["https://cdn.example/a.jpg"],
                "subcategoria_id": str(uuid4()),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["estado"] == EstadoSolicitud.PUBLICADA.value
        assert body["num_profesionales_notificados"] == 0
        assert body["subcategoria_id"] is None
        assert body["fotos_urls"] == ["https://cdn.example/a.jpg"]
        assert body["cliente_nombre"] == "Ana Cliente"
        assert body["zona_ciudad"] == "Barranquilla"

        listed = await test_client.get("/api/v1/solicitudes/", headers=headers)
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_profesional_sees_open_matching_only(
        self, test_client, db_session, create_user: Callable[..., Awaitable[User]]
    ):
        await _seed_catalog(db_session)
        cliente, _ = await _cliente_auth(db_session, create_user)
        _, pro_headers = await _profesional_auth(db_session, create_user)

        match = Solicitud(
            cliente_id=cliente.id,
            categoria_id=CAT_ID,
            descripcion="Match",
            zona_id=ZONA_ID,
        )
        other_cat = Solicitud(
            cliente_id=cliente.id,
            categoria_id=OTHER_CAT_ID,
            descripcion="Other cat",
            zona_id=ZONA_ID,
        )
        db_session.add_all([match, other_cat])
        await db_session.commit()

        listed = await test_client.get("/api/v1/solicitudes/", headers=pro_headers)
        assert listed.status_code == status.HTTP_200_OK
        items = listed.json()["items"]
        assert [i["descripcion"] for i in items] == ["Match"]
        assert items[0]["cliente_nombre"] == "Ana Cliente"

        detail = await test_client.get(
            f"/api/v1/solicitudes/{match.id}", headers=pro_headers
        )
        assert detail.status_code == status.HTTP_200_OK

        hidden = await test_client.get(
            f"/api/v1/solicitudes/{other_cat.id}", headers=pro_headers
        )
        assert hidden.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio(loop_scope="function")
    async def test_cancel_copies_motivo_to_open_propuestas(
        self, test_client, db_session, create_user: Callable[..., Awaitable[User]]
    ):
        await _seed_catalog(db_session)
        cliente, headers = await _cliente_auth(db_session, create_user)
        pro, _ = await _profesional_auth(db_session, create_user)

        solicitud = Solicitud(
            cliente_id=cliente.id,
            categoria_id=CAT_ID,
            descripcion="Cancelame",
            zona_id=ZONA_ID,
            estado=EstadoSolicitud.CON_PROPUESTAS.value,
        )
        db_session.add(solicitud)
        await db_session.commit()

        abierta = Propuesta(
            solicitud_id=solicitud.id,
            profesional_id=pro.id,
            precio_inicial="100000.00",
            estado=EstadoPropuesta.ENVIADA.value,
        )
        db_session.add(abierta)
        await db_session.commit()

        response = await test_client.post(
            f"/api/v1/solicitudes/{solicitud.id}/cancelar",
            headers=headers,
            json={"motivo_cancelamiento": "cliente_cancelo_solicitud"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["estado"] == EstadoSolicitud.CANCELADA.value
        assert response.json()["motivo_cancelamiento"] == "cliente_cancelo_solicitud"

        propuesta = (
            await db_session.execute(
                select(Propuesta).where(Propuesta.id == abierta.id)
            )
        ).scalar_one()
        assert propuesta.estado == EstadoPropuesta.CANCELADA.value
        assert propuesta.motivo_cancelamiento == "cliente_cancelo_solicitud"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_cancel_pagada_conflict(
        self, test_client, db_session, create_user: Callable[..., Awaitable[User]]
    ):
        await _seed_catalog(db_session)
        cliente, headers = await _cliente_auth(db_session, create_user)
        solicitud = Solicitud(
            cliente_id=cliente.id,
            categoria_id=CAT_ID,
            descripcion="Pagada",
            zona_id=ZONA_ID,
            estado=EstadoSolicitud.PAGADA.value,
        )
        db_session.add(solicitud)
        await db_session.commit()

        response = await test_client.post(
            f"/api/v1/solicitudes/{solicitud.id}/cancelar",
            headers=headers,
            json={},
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio(loop_scope="function")
    async def test_user_without_profile_forbidden(
        self, test_client, authenticated_user
    ):
        response = await test_client.get(
            "/api/v1/solicitudes/", headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
