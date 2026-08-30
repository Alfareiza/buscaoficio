from typing import Any, AsyncGenerator
from urllib.parse import urlparse

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base, User

# statement_cache_size=0: asyncpg's own cache.
# prepared_statement_cache_size=0: SQLAlchemy's LRU of PreparedStatement
# objects (separate from asyncpg; default 100).
# prepared_statement_name_func=str: SQLAlchemy still calls
# connection.prepare(); a None name becomes a named __asyncpg_stmt_N__
# in asyncpg 0.29 (BUSCAOFICIO-BACKEND-W). str() is "" — unnamed
# prepares, which PgBouncer transaction mode can recycle. Builtin, not
# a project function or lambda.
#
# ssl="prefer": encrypts when the server offers it, plaintext otherwise.
# Local Docker Postgres has no SSL; Supabase (prod, temporary) and RDS
# (after launch, rds.force_ssl=1) both do. One setting, no env branching.
#
# Alembic's engine in alembic_migrations/env.py imports this dict.
ASYNC_CONNECT_ARGS: dict[str, Any] = {
    "ssl": "prefer",
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
    "prepared_statement_name_func": str,
}

parsed_db_url = urlparse(settings.DATABASE_URL)

# Disable connection pooling — uniform across dev and prod.
engine = create_async_engine(
    f"postgresql+asyncpg://{parsed_db_url.username}:{parsed_db_url.password}@"
    f"{parsed_db_url.hostname}{':' + str(parsed_db_url.port) if parsed_db_url.port else ''}"
    f"{parsed_db_url.path}",
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
