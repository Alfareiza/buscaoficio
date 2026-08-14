"""clientes_profesionales_shared_pk

Revision ID: c78a3f6efeb3
Revises: 38130b781202
Create Date: 2026-08-14 10:33:13.821310

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c78a3f6efeb3"
down_revision: Union[str, None] = "38130b781202"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate detected dropping 'id' but did not add a replacement
    # primary key on usuario_id — without create_primary_key below, both
    # tables would end up with NO primary key at all. Order matters: drop
    # the old FK before dropping 'id' (its target), create the new PK
    # before the new FK (which references it).
    op.drop_constraint("clientes_usuario_id_key", "clientes", type_="unique")
    op.drop_constraint("clientes_referido_por_id_fkey", "clientes", type_="foreignkey")
    op.drop_column("clientes", "id")
    op.create_primary_key("clientes_pkey", "clientes", ["usuario_id"])
    op.create_foreign_key(
        "clientes_referido_por_id_fkey",
        "clientes",
        "clientes",
        ["referido_por_id"],
        ["usuario_id"],
    )

    op.drop_constraint("profesionales_usuario_id_key", "profesionales", type_="unique")
    op.drop_column("profesionales", "id")
    op.create_primary_key("profesionales_pkey", "profesionales", ["usuario_id"])


def downgrade() -> None:
    # NOTE: only safe while clientes/profesionales are empty — re-adding
    # 'id' as NOT NULL with no default/backfill will fail once rows exist.
    op.drop_constraint("profesionales_pkey", "profesionales", type_="primary")
    op.add_column(
        "profesionales", sa.Column("id", sa.UUID(), autoincrement=False, nullable=False)
    )
    op.create_primary_key("profesionales_pkey", "profesionales", ["id"])
    op.create_unique_constraint(
        "profesionales_usuario_id_key", "profesionales", ["usuario_id"]
    )

    op.drop_constraint("clientes_referido_por_id_fkey", "clientes", type_="foreignkey")
    op.drop_constraint("clientes_pkey", "clientes", type_="primary")
    op.add_column(
        "clientes", sa.Column("id", sa.UUID(), autoincrement=False, nullable=False)
    )
    op.create_primary_key("clientes_pkey", "clientes", ["id"])
    op.create_foreign_key(
        "clientes_referido_por_id_fkey",
        "clientes",
        "clientes",
        ["referido_por_id"],
        ["id"],
    )
    op.create_unique_constraint("clientes_usuario_id_key", "clientes", ["usuario_id"])
