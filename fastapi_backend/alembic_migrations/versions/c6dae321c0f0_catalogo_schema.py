"""catalogo_schema

Revision ID: c6dae321c0f0
Revises: c8f3a91d4e20
Create Date: 2026-09-10 01:18:26.067869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6dae321c0f0"
down_revision: Union[str, None] = "c8f3a91d4e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categorias_servicio",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("complejidad", sa.String(length=10), nullable=False),
        sa.Column("activa_v1", sa.Boolean(), nullable=False),
        sa.Column("orden_display", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "zonas_cobertura",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ciudad", sa.String(length=100), nullable=False),
        sa.Column("localidad", sa.String(length=100), nullable=True),
        sa.Column("activa_v1", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subcategorias_servicio",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias_servicio.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "profesional_categoria",
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias_servicio.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["profesionales.usuario_id"]),
        sa.PrimaryKeyConstraint("usuario_id", "categoria_id"),
    )
    op.create_table(
        "profesional_zona",
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("zona_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["profesionales.usuario_id"]),
        sa.ForeignKeyConstraint(["zona_id"], ["zonas_cobertura.id"]),
        sa.PrimaryKeyConstraint("usuario_id", "zona_id"),
    )
    op.add_column("clientes", sa.Column("zona_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "clientes_zona_id_fkey",
        "clientes",
        "zonas_cobertura",
        ["zona_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("clientes_zona_id_fkey", "clientes", type_="foreignkey")
    op.drop_column("clientes", "zona_id")
    op.drop_table("profesional_zona")
    op.drop_table("profesional_categoria")
    op.drop_table("subcategorias_servicio")
    op.drop_table("zonas_cobertura")
    op.drop_table("categorias_servicio")
