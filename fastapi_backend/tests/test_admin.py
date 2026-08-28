"""Tests for ``UserAdmin.authenticate`` and ``UserAdmin.change_password``."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin import UserAdmin
from app.models import User
from tests.conftest import DEFAULT_USER_PASSWORD

NEW_PASSWORD = "NewPassword456#"


@pytest.fixture
def user_admin(engine, mocker) -> UserAdmin:
    """Return a UserAdmin instance that uses the test database engine.

    :param engine: Per-test async engine from conftest.
    :param mocker: pytest-mock fixture used to patch ``get_sessionmaker``.
    :return: UserAdmin bound to the test sessionmaker.
    """
    test_sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    mocker.patch.object(UserAdmin, "get_sessionmaker", return_value=test_sessionmaker)
    return UserAdmin(User)


class TestUserAdminAuthenticate:
    """Tests for ``UserAdmin.authenticate``."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_id_for_superuser_with_valid_password(
        self, user_admin: UserAdmin, superuser: User
    ):
        """Return the superuser id when email and password are valid."""
        result = await user_admin.authenticate(superuser.email, DEFAULT_USER_PASSWORD)

        assert result == superuser.id

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_none_for_wrong_password(
        self, user_admin: UserAdmin, superuser: User
    ):
        """Return None when the password does not match."""
        result = await user_admin.authenticate(superuser.email, "WrongPassword1#")

        assert result is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_none_for_unknown_email(self, user_admin: UserAdmin):
        """Return None when no superuser exists for the given email."""
        result = await user_admin.authenticate(
            "missing@example.com", DEFAULT_USER_PASSWORD
        )

        assert result is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_none_for_non_superuser(
        self, user_admin: UserAdmin, create_user
    ):
        """Return None when the credentials belong to a regular user."""
        user = await create_user()

        result = await user_admin.authenticate(user.email, DEFAULT_USER_PASSWORD)

        assert result is None


class TestUserAdminSoftDelete:
    """Tests for soft-delete via FastAdmin."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_delete_model_sets_deleted_at(
        self, user_admin: UserAdmin, create_user, db_session
    ):
        """Keep the row and stamp deleted_at instead of removing it."""
        user = await create_user(email="admin-delete@example.com")

        await user_admin.delete_model(user.id)

        await db_session.refresh(user)
        assert user.deleted_at is not None
        assert user.is_active is False

    @pytest.mark.asyncio(loop_scope="function")
    async def test_list_hides_deleted_users(self, user_admin: UserAdmin, create_user):
        """Omit tombstones from the Usuarios list."""
        live = await create_user(email="live@example.com")
        gone = await create_user(email="gone@example.com")
        await user_admin.delete_model(gone.id)

        objs, total = await user_admin.orm_get_list()

        ids = {obj.id for obj in objs}
        assert live.id in ids
        assert gone.id not in ids
        assert total == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_get_obj_returns_none_for_deleted_user(
        self, user_admin: UserAdmin, create_user
    ):
        """Change-page fetch of a tombstone looks like a missing row."""
        user = await create_user(email="hidden@example.com")
        await user_admin.delete_model(user.id)

        assert await user_admin.orm_get_obj(user.id) is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_authenticate_rejects_deleted_superuser(
        self, user_admin: UserAdmin, superuser: User
    ):
        """A soft-deleted superuser cannot sign into /admin."""
        await user_admin.delete_model(superuser.id)

        result = await user_admin.authenticate(superuser.email, DEFAULT_USER_PASSWORD)

        assert result is None


class TestUserAdminChangePassword:
    """Tests for ``UserAdmin.change_password``."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_new_password_authenticates(
        self, user_admin: UserAdmin, superuser: User
    ):
        """Allow login with the new password after a change."""
        await user_admin.change_password(superuser.id, NEW_PASSWORD)

        result = await user_admin.authenticate(superuser.email, NEW_PASSWORD)
        assert result == superuser.id

    @pytest.mark.asyncio(loop_scope="function")
    async def test_old_password_no_longer_authenticates(
        self, user_admin: UserAdmin, superuser: User
    ):
        """Reject the previous password after a change."""
        await user_admin.change_password(superuser.id, NEW_PASSWORD)

        result = await user_admin.authenticate(superuser.email, DEFAULT_USER_PASSWORD)
        assert result is None
