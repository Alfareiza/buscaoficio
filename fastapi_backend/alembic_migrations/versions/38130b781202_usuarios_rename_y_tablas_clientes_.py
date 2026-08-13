"""usuarios rename y tablas clientes profesionales

Revision ID: 38130b781202
Revises: b389592974f8
Create Date: 2026-08-13 17:31:03.044981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38130b781202'
down_revision: Union[str, None] = 'b389592974f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename in place (preserves data + the existing FK from items,
    # which Postgres tracks by OID, not by name).
    op.rename_table('user', 'usuarios')
    op.execute('ALTER INDEX ix_user_email RENAME TO ix_usuarios_email')
    op.execute('ALTER TABLE usuarios RENAME CONSTRAINT user_pkey TO usuarios_pkey')

    op.add_column('usuarios', sa.Column('nombre_completo', sa.String(), nullable=True))
    op.execute('UPDATE usuarios SET nombre_completo = email WHERE nombre_completo IS NULL')
    op.alter_column('usuarios', 'nombre_completo', nullable=False)

    op.add_column('usuarios', sa.Column('whatsapp', sa.String(), nullable=True))
    op.add_column(
        'usuarios',
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.add_column(
        'usuarios',
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table('clientes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=False),
    sa.Column('direccion_default', sa.String(), nullable=True),
    sa.Column('repeat_customer', sa.Boolean(), nullable=False),
    sa.Column('referido_por_id', sa.UUID(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['referido_por_id'], ['clientes.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('usuario_id')
    )
    op.create_table('profesionales',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=False),
    sa.Column('documento_tipo', sa.String(), nullable=False),
    sa.Column('documento_numero', sa.String(), nullable=False),
    sa.Column('anos_experiencia', sa.Integer(), nullable=True),
    sa.Column('foto_perfil_url', sa.String(), nullable=True),
    sa.Column('terminos_aceptados', sa.Boolean(), nullable=False),
    sa.Column('terminos_aceptados_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('score_calificacion', sa.Integer(), nullable=True),
    sa.Column('estado_verificacion', sa.String(), nullable=False),
    sa.Column('whatsapp_verificado', sa.Boolean(), nullable=False),
    sa.Column('contrato_aceptado', sa.Boolean(), nullable=False),
    sa.Column('contrato_aceptado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('contrato_aceptado_ip', sa.String(), nullable=True),
    sa.Column('trabajos_gratis_restantes', sa.Integer(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('documento_numero'),
    sa.UniqueConstraint('usuario_id')
    )


def downgrade() -> None:
    op.drop_table('profesionales')
    op.drop_table('clientes')

    op.drop_column('usuarios', 'actualizado_en')
    op.drop_column('usuarios', 'creado_en')
    op.drop_column('usuarios', 'whatsapp')
    op.drop_column('usuarios', 'nombre_completo')

    op.execute('ALTER TABLE usuarios RENAME CONSTRAINT usuarios_pkey TO user_pkey')
    op.execute('ALTER INDEX ix_usuarios_email RENAME TO ix_user_email')
    op.rename_table('usuarios', 'user')
