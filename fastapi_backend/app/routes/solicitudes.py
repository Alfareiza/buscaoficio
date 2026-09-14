from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import User, get_async_session
from app.enums import (
    PROPUESTA_ABIERTA,
    SOLICITUD_ABIERTA,
    EstadoSolicitud,
    EstadoPropuesta,
)
from app.models import (
    CategoriaServicio,
    Cliente,
    Profesional,
    ProfesionalCategoria,
    ProfesionalZona,
    Propuesta,
    Solicitud,
    ZonaCobertura,
)
from app.schemas import SolicitudCancel, SolicitudCreate, SolicitudRead
from app.users import current_active_user

router = APIRouter(tags=["solicitudes"])

_CANCELABLE = (EstadoSolicitud.PUBLICADA.value, EstadoSolicitud.CON_PROPUESTAS.value)


def _to_read(solicitud: Solicitud) -> SolicitudRead:
    cliente_nombre = None
    if solicitud.cliente is not None and solicitud.cliente.usuario is not None:
        cliente_nombre = solicitud.cliente.usuario.nombre_completo
    zona_ciudad = solicitud.zona.ciudad if solicitud.zona is not None else None
    return SolicitudRead.model_validate(solicitud).model_copy(
        update={"cliente_nombre": cliente_nombre, "zona_ciudad": zona_ciudad}
    )


def _list_load():
    return (
        joinedload(Solicitud.cliente).joinedload(Cliente.usuario),
        joinedload(Solicitud.zona),
    )


async def _profiles(
    db: AsyncSession, user_id: UUID
) -> tuple[Cliente | None, Profesional | None]:
    cliente = (
        await db.execute(select(Cliente).where(Cliente.usuario_id == user_id))
    ).scalar_one_or_none()
    profesional = (
        await db.execute(select(Profesional).where(Profesional.usuario_id == user_id))
    ).scalar_one_or_none()
    return cliente, profesional


def _profesional_feed_query(user_id: UUID):
    return (
        select(Solicitud)
        .options(*_list_load())
        .where(
            Solicitud.estado.in_([e.value for e in SOLICITUD_ABIERTA]),
            Solicitud.categoria_id.in_(
                select(ProfesionalCategoria.categoria_id).where(
                    ProfesionalCategoria.usuario_id == user_id
                )
            ),
            Solicitud.zona_id.in_(
                select(ProfesionalZona.zona_id).where(
                    ProfesionalZona.usuario_id == user_id
                )
            ),
        )
        .order_by(Solicitud.creado_en.desc())
    )


@router.get(
    "/",
    summary="Paginated solicitudes (cliente: own; profesional: open feed)",
    response_model=Page[SolicitudRead],
)
async def list_solicitudes(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    cliente, profesional = await _profiles(db, user.id)
    if cliente is not None:
        query = (
            select(Solicitud)
            .options(*_list_load())
            .where(Solicitud.cliente_id == user.id)
            .order_by(Solicitud.creado_en.desc())
        )
    elif profesional is not None:
        query = _profesional_feed_query(user.id)
    else:
        raise HTTPException(
            status_code=403, detail="Se requiere perfil cliente o profesional"
        )

    return await apaginate(
        db,
        query,
        Params(page=page, size=size),
        transformer=lambda rows: [_to_read(s) for s in rows],
    )


@router.post(
    "/",
    summary="Create solicitud (cliente)",
    response_model=SolicitudRead,
    status_code=201,
)
async def create_solicitud(
    payload: SolicitudCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    cliente, _ = await _profiles(db, user.id)
    if cliente is None:
        raise HTTPException(status_code=403, detail="Se requiere perfil cliente")

    categoria = await db.get(CategoriaServicio, payload.categoria_id)
    zona = await db.get(ZonaCobertura, payload.zona_id)
    if categoria is None or zona is None:
        raise HTTPException(status_code=400, detail="categoria_id o zona_id inválidos")

    solicitud = Solicitud(
        cliente_id=user.id,
        categoria_id=payload.categoria_id,
        subcategoria_id=None,
        descripcion=payload.descripcion,
        fotos_urls=payload.fotos_urls,
        presupuesto_aproximado=payload.presupuesto_aproximado,
        es_urgente=payload.es_urgente,
        zona_id=payload.zona_id,
    )
    db.add(solicitud)
    await db.commit()
    result = await db.execute(
        select(Solicitud).options(*_list_load()).where(Solicitud.id == solicitud.id)
    )
    return _to_read(result.scalar_one())


@router.get(
    "/{solicitud_id}",
    summary="Solicitud detail (owner or matching profesional)",
    response_model=SolicitudRead,
)
async def get_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    cliente, profesional = await _profiles(db, user.id)
    if cliente is None and profesional is None:
        raise HTTPException(
            status_code=403, detail="Se requiere perfil cliente o profesional"
        )

    result = await db.execute(
        select(Solicitud).options(*_list_load()).where(Solicitud.id == solicitud_id)
    )
    solicitud = result.scalar_one_or_none()
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if cliente is not None and solicitud.cliente_id == user.id:
        return _to_read(solicitud)

    if profesional is not None:
        allowed = await db.execute(
            _profesional_feed_query(user.id).where(Solicitud.id == solicitud_id)
        )
        if allowed.scalar_one_or_none() is not None:
            return _to_read(solicitud)

    raise HTTPException(status_code=404, detail="Solicitud no encontrada")


@router.post(
    "/{solicitud_id}/cancelar",
    summary="Cancel solicitud (cliente, publicada or con_propuestas)",
    response_model=SolicitudRead,
)
async def cancel_solicitud(
    solicitud_id: UUID,
    payload: SolicitudCancel,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    cliente, _ = await _profiles(db, user.id)
    if cliente is None:
        raise HTTPException(status_code=403, detail="Se requiere perfil cliente")

    result = await db.execute(
        select(Solicitud)
        .options(*_list_load())
        .where(Solicitud.id == solicitud_id, Solicitud.cliente_id == user.id)
    )
    solicitud = result.scalar_one_or_none()
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado not in _CANCELABLE:
        raise HTTPException(
            status_code=409, detail="La solicitud no se puede cancelar en este estado"
        )

    solicitud.estado = EstadoSolicitud.CANCELADA.value
    solicitud.motivo_cancelamiento = payload.motivo_cancelamiento

    propuestas = (
        (
            await db.execute(
                select(Propuesta).where(
                    Propuesta.solicitud_id == solicitud.id,
                    Propuesta.estado.in_([e.value for e in PROPUESTA_ABIERTA]),
                )
            )
        )
        .scalars()
        .all()
    )
    for propuesta in propuestas:
        propuesta.estado = EstadoPropuesta.CANCELADA.value
        propuesta.motivo_cancelamiento = payload.motivo_cancelamiento

    await db.commit()
    refreshed = await db.execute(
        select(Solicitud).options(*_list_load()).where(Solicitud.id == solicitud.id)
    )
    return _to_read(refreshed.scalar_one())
