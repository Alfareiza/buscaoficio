"""add used_google_session_tokens table

Revision ID: 67f2b3cd225f
Revises: 938ad64baf39
Create Date: 2026-08-23 11:43:47.453189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import fastapi_users_db_sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '67f2b3cd225f'
down_revision: Union[str, None] = '938ad64baf39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: autogenerate also proposed dropping ix_refresh_tokens_expires_at
    # and ix_refresh_tokens_user_id (same pre-existing, unrelated drift
    # already excluded from migration 938ad64baf39) — removed here too, to
    # keep this migration scoped to the new table only.
    op.create_table('used_google_session_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('jti', sa.String(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_used_google_session_tokens_jti'), 'used_google_session_tokens', ['jti'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_used_google_session_tokens_jti'), table_name='used_google_session_tokens')
    op.drop_table('used_google_session_tokens')
