"""catalogo_seed

Revision ID: a1b2c3d4e5f6
Revises: c6dae321c0f0
Create Date: 2026-09-10 01:20:00.000000

Seed from AuthBrandPanel SERVICIOS (all activa_v1=false) + Barranquilla zona.
"""
from typing import Sequence, Union
from uuid import UUID

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c6dae321c0f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches nextjs-frontend/components/auth/AuthBrandPanel.tsx SERVICIOS titles.
# Complejidad is a first-pass assignment for triaje calibration; editable in admin.
# Fixed UUIDs so upgrade/downgrade stay stable across imports.
CATEGORIAS: list[tuple[UUID, str, str, int]] = [
    (UUID("11111111-1111-4111-8111-111111110001"), "Pintura", "baja", 1),
    (UUID("11111111-1111-4111-8111-111111110002"), "Limpieza", "baja", 2),
    (UUID("11111111-1111-4111-8111-111111110003"), "Carpintería", "media", 3),
    (UUID("11111111-1111-4111-8111-111111110004"), "Electricidad", "alta", 4),
    (UUID("11111111-1111-4111-8111-111111110005"), "Cerrajería", "media", 5),
    (UUID("11111111-1111-4111-8111-111111110006"), "Instalaciones", "media", 6),
    (UUID("11111111-1111-4111-8111-111111110007"), "Reparaciones", "media", 7),
    (UUID("11111111-1111-4111-8111-111111110008"), "Programación", "alta", 8),
    (UUID("11111111-1111-4111-8111-111111110009"), "Obra blanca", "alta", 9),
    (UUID("11111111-1111-4111-8111-11111111000a"), "Aires acondicionados", "alta", 10),
    (UUID("11111111-1111-4111-8111-11111111000b"), "Jardinería", "baja", 11),
]

ZONA_BARRANQUILLA_ID = UUID("22222222-2222-4222-8222-222222222001")


def upgrade() -> None:
    categorias = sa.table(
        "categorias_servicio",
        sa.column("id", sa.UUID),
        sa.column("nombre", sa.String),
        sa.column("complejidad", sa.String),
        sa.column("activa_v1", sa.Boolean),
        sa.column("orden_display", sa.SmallInteger),
    )
    op.bulk_insert(
        categorias,
        [
            {
                "id": cat_id,
                "nombre": nombre,
                "complejidad": complejidad,
                "activa_v1": False,
                "orden_display": orden,
            }
            for cat_id, nombre, complejidad, orden in CATEGORIAS
        ],
    )

    zonas = sa.table(
        "zonas_cobertura",
        sa.column("id", sa.UUID),
        sa.column("ciudad", sa.String),
        sa.column("localidad", sa.String),
        sa.column("activa_v1", sa.Boolean),
    )
    op.bulk_insert(
        zonas,
        [
            {
                "id": ZONA_BARRANQUILLA_ID,
                "ciudad": "Barranquilla",
                "localidad": None,
                "activa_v1": True,
            }
        ],
    )


def downgrade() -> None:
    ids = ", ".join(f"'{cat_id}'" for cat_id, _, _, _ in CATEGORIAS)
    op.execute(sa.text(f"DELETE FROM categorias_servicio WHERE id IN ({ids})"))
    op.execute(
        sa.text(
            f"DELETE FROM zonas_cobertura WHERE id = '{ZONA_BARRANQUILLA_ID}'"
        )
    )
