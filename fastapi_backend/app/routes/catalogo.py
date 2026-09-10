from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_async_session
from app.models import CategoriaServicio, ZonaCobertura
from app.schemas import CategoriaServicioRead, ZonaCoberturaRead

router = APIRouter(tags=["catalogo"])


@router.get(
    "/categorias",
    summary="List service categories (public)",
    response_model=list[CategoriaServicioRead],
)
async def list_categorias(
    db: AsyncSession = Depends(get_async_session),
):
    """Return all service categories ordered by display order."""
    result = await db.execute(
        select(CategoriaServicio).order_by(
            CategoriaServicio.orden_display.nulls_last(),
            CategoriaServicio.nombre,
        )
    )
    return result.scalars().all()


@router.get(
    "/zonas",
    summary="List coverage zones (public)",
    response_model=list[ZonaCoberturaRead],
)
async def list_zonas(
    db: AsyncSession = Depends(get_async_session),
):
    """Return all coverage zones ordered by city."""
    result = await db.execute(
        select(ZonaCobertura).order_by(ZonaCobertura.ciudad, ZonaCobertura.localidad)
    )
    return result.scalars().all()
