"""add google_sub to usuarios

Revision ID: 938ad64baf39
Revises: a067ad066d81
Create Date: 2026-08-22 16:22:23.105249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import fastapi_users_db_sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '938ad64baf39'
down_revision: Union[str, None] = 'a067ad066d81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: autogenerate also proposed dropping ix_refresh_tokens_expires_at
    # and ix_refresh_tokens_user_id (pre-existing drift between the DB and
    # models.py, unrelated to this change) — removed from this migration to
    # keep it scoped to the google_sub addition only.
    op.add_column('usuarios', sa.Column('google_sub', sa.String(), nullable=True))
    op.create_unique_constraint('usuarios_google_sub_key', 'usuarios', ['google_sub'])


def downgrade() -> None:
    op.drop_constraint('usuarios_google_sub_key', 'usuarios', type_='unique')
    op.drop_column('usuarios', 'google_sub')
