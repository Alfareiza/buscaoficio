"""add usuarios.deleted_at

Revision ID: c8f3a91d4e20
Revises: 559a743e2312
Create Date: 2026-08-28 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8f3a91d4e20"
down_revision: Union[str, None] = "559a743e2312"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "deleted_at")
