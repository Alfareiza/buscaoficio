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
        result = await user_admin.authenticate("missing@example.com", DEFAULT_USER_PASSWORD)

        assert result is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_none_for_non_superuser(
        self, user_admin: UserAdmin, create_user
    ):
        """Return None when the credentials belong to a regular user."""
        user = await create_user()

        result = await user_admin.authenticate(user.email, DEFAULT_USER_PASSWORD)

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
