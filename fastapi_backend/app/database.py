from typing import AsyncGenerator
from urllib.parse import urlparse

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base, User


parsed_db_url = urlparse(settings.DATABASE_URL)

async_db_connection_url = (
    f"postgresql+asyncpg://{parsed_db_url.username}:{parsed_db_url.password}@"
    f"{parsed_db_url.hostname}{':' + str(parsed_db_url.port) if parsed_db_url.port else ''}"
    f"{parsed_db_url.path}"
)

# Shared with alembic_migrations/env.py — keep them in lockstep.
#
# ssl="prefer": encrypts when the server offers it, plaintext otherwise.
# Local Docker Postgres has no SSL; Supabase (prod, temporary) and RDS
# (after launch, rds.force_ssl=1) both do. One setting, no env branching.
#
# statement_cache_size=0: asyncpg prepared statements are unsafe through
# PgBouncer transaction mode (Supabase pooler :6543). NullPool opens a
# new client connection per request; the pooler reuses the backend, so
# default names (__asyncpg_stmt_N__) collide
# (BUSCAOFICIO-BACKEND-T / DuplicatePreparedStatementError). Harmless
# on a direct Postgres connection (local :5434, RDS 5432).
ASYNC_CONNECT_ARGS: dict[str, str | int] = {
    "ssl": "prefer",
    "statement_cache_size": 0,
}

# Disable connection pooling — uniform across dev and prod.
engine = create_async_engine(
    async_db_connection_url,
    poolclass=NullPool,
    connect_args=ASYNC_CONNECT_ARGS,
)

async_session_maker = async_sessionmaker(
    engine, expire_on_commit=settings.EXPIRE_ON_COMMIT
)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
