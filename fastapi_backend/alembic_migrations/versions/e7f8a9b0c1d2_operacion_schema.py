"""operacion_schema

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "solicitudes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cliente_id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=False),
        sa.Column("subcategoria_id", sa.UUID(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("fotos_urls", sa.JSON(), nullable=True),
        sa.Column("presupuesto_aproximado", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "es_urgente", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "estado", sa.String(length=30), nullable=False, server_default="publicada"
        ),
        sa.Column(
            "num_profesionales_notificados",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("primera_propuesta_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("zona_id", sa.UUID(), nullable=False),
        sa.Column("motivo_cancelamiento", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias_servicio.id"]),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.usuario_id"]),
        sa.ForeignKeyConstraint(["subcategoria_id"], ["subcategorias_servicio.id"]),
        sa.ForeignKeyConstraint(["zona_id"], ["zonas_cobertura.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "propuestas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("profesional_id", sa.UUID(), nullable=False),
        sa.Column("precio_inicial", sa.Numeric(12, 2), nullable=False),
        sa.Column("plazo_ejecucion_dias", sa.SmallInteger(), nullable=True),
        sa.Column("descripcion_enfoque", sa.Text(), nullable=True),
        sa.Column(
            "estado", sa.String(length=30), nullable=False, server_default="enviada"
        ),
        sa.Column("motivo_cancelamiento", sa.Text(), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plazo_ejecucion_dias IS NULL OR plazo_ejecucion_dias >= 1",
            name="propuestas_plazo_min_1",
        ),
        sa.ForeignKeyConstraint(["profesional_id"], ["profesionales.usuario_id"]),
        sa.ForeignKeyConstraint(["solicitud_id"], ["solicitudes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "negociaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("propuesta_id", sa.UUID(), nullable=False),
        sa.Column("ronda", sa.SmallInteger(), nullable=False),
        sa.Column("iniciada_por", sa.String(length=20), nullable=False),
        sa.Column("precio_propuesto", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "resultado",
            sa.String(length=20),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ronda <= 2", name="negociaciones_ronda_max_2"),
        sa.CheckConstraint("precio_propuesto > 0", name="negociaciones_precio_positivo"),
        sa.ForeignKeyConstraint(["propuesta_id"], ["propuestas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("negociaciones")
    op.drop_table("propuestas")
    op.drop_table("solicitudes")
