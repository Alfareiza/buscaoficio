from collections.abc import Awaitable, Callable
import uuid

from httpx import AsyncClient, ASGITransport
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.password import PasswordHelper

from app.config import settings
from app.models import User, Base

from app.database import get_user_db, get_async_session
from app.main import app
from app.users import get_jwt_strategy

DEFAULT_USER_EMAIL = "test@example.com"
DEFAULT_USER_PASSWORD = "TestPassword123#"


async def issue_auth_headers(user: User) -> dict[str, str]:
    """Return a Bearer Authorization header for ``user``.

    :param user: Persisted user to encode in the JWT.
    :return: Header dict suitable for httpx ``headers=``.
    """
    token = await get_jwt_strategy().write_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create a fresh test database engine for each test function."""
    engine = create_async_engine(settings.TEST_DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine):
    """Create a fresh database session for each test."""
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture(scope="function")
async def test_client(db_session):
    """Fixture to create a test client that uses the test database session."""

    # FastAPI-Users database override (wraps session with user operation helpers)
    async def override_get_user_db():
        session = SQLAlchemyUserDatabase(db_session, User)
        try:
            yield session
        finally:
            await db_session.close()

    # General database override (raw session access)
    async def override_get_async_session():
        try:
            yield db_session
        finally:
            await db_session.close()

    # Set up test database overrides
    app.dependency_overrides[get_user_db] = override_get_user_db
    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://localhost:8001"
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def create_user(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    """Return a factory that inserts a user, overriding only the fields you pass.

    :return: Async callable that persists a ``User`` and returns it.
    """

    async def _create_user(
        *,
        email: str = DEFAULT_USER_EMAIL,
        password: str = DEFAULT_USER_PASSWORD,
        nombre_completo: str = "Test User",
        is_superuser: bool = False,
        is_active: bool = True,
        is_verified: bool = True,
    ) -> User:
        """Insert a user into the test database.

        :param email: Unique email for the user.
        :param password: Plaintext password to hash and store.
        :param nombre_completo: Full name (required, non-nullable column).
        :param is_superuser: Whether the user has admin privileges.
        :param is_active: Whether the user can authenticate.
        :param is_verified: Whether the email is verified.
        :return: The persisted User instance.
        """
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=PasswordHelper().hash(password),
            nombre_completo=nombre_completo,
            is_active=is_active,
            is_superuser=is_superuser,
            is_verified=is_verified,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create_user


@pytest_asyncio.fixture(scope="function")
async def superuser(create_user: Callable[..., Awaitable[User]]) -> User:
    """Return a persisted superuser with ``DEFAULT_USER_PASSWORD``.

    :param create_user: Shared user factory fixture.
    :return: The persisted superuser.
    """
    return await create_user(email="admin@example.com", is_superuser=True)


@pytest_asyncio.fixture(scope="function")
async def authenticated_user(test_client, create_user: Callable[..., Awaitable[User]]):
    """Create a regular user and return auth headers plus the user payload.

    :param test_client: Ensures FastAPI dependency overrides are in place.
    :param create_user: Shared user factory fixture.
    :return: Dict with ``headers``, ``user``, and ``user_data``.
    """
    user = await create_user()
    return {
        "headers": await issue_auth_headers(user),
        "user": user,
        "user_data": {"email": user.email, "password": DEFAULT_USER_PASSWORD},
    }


@pytest_asyncio.fixture(scope="function")
async def authenticated_superuser(test_client, superuser: User):
    """Create a superuser and return auth headers plus the user payload.

    :param test_client: Ensures FastAPI dependency overrides are in place.
    :param superuser: Persisted superuser fixture.
    :return: Dict with ``headers``, ``user``, and ``user_data``.
    """
    return {
        "headers": await issue_auth_headers(superuser),
        "user": superuser,
        "user_data": {"email": superuser.email, "password": DEFAULT_USER_PASSWORD},
    }
