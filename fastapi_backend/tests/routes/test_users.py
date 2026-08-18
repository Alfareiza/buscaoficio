"""HTTP tests for the ``/users`` routes."""

import uuid

import pytest
from fastapi import status
from fastapi_users.password import PasswordHelper
from fastapi_users.router.common import ErrorCode
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Item, User
from tests.conftest import DEFAULT_USER_PASSWORD, issue_auth_headers

MISSING_USER_ID = "00000000-0000-0000-0000-000000000000"
NEW_EMAIL = "updated@example.com"
NEW_PASSWORD = "NewPassword456#"
USER_READ_FIELDS = {
    "id",
    "email",
    "is_active",
    "is_superuser",
    "is_verified",
    "nombre_completo",
    "whatsapp",
}


def assert_user_payload(payload: dict, user: User, **overrides) -> None:
    """Assert a UserRead JSON body matches ``user``.

    :param payload: Parsed JSON response.
    :param user: Persisted user used as the baseline.
    :param overrides: Field values expected after a mutation.
    """
    assert set(payload) == USER_READ_FIELDS
    assert payload["id"] == str(user.id)
    assert payload["email"] == overrides.get("email", user.email)
    assert payload["is_active"] is overrides.get("is_active", user.is_active)
    assert payload["is_superuser"] is overrides.get("is_superuser", user.is_superuser)
    assert payload["is_verified"] is overrides.get("is_verified", user.is_verified)


class TestUsersAuthentication:
    """Anonymous callers must not reach any /users endpoint."""

    @pytest.mark.parametrize(
        "method, path",
        [
            ("GET", "/api/v1/users/me"),
            ("PATCH", "/api/v1/users/me"),
            ("GET", f"/api/v1/users/{MISSING_USER_ID}"),
            ("PATCH", f"/api/v1/users/{MISSING_USER_ID}"),
            ("DELETE", f"/api/v1/users/{MISSING_USER_ID}"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="function")
    async def test_anonymous_request_returns_401(
        self, test_client: AsyncClient, method: str, path: str
    ):
        """Return 401 when no Authorization header is sent."""
        response = await test_client.request(method, path, json={})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUsersAuthorization:
    """Regular users must not call superuser-only /users/{id} routes."""

    @pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
    @pytest.mark.asyncio(loop_scope="function")
    async def test_regular_user_cannot_access_user_by_id(
        self, test_client: AsyncClient, authenticated_user: dict, method: str
    ):
        """Return 403 when a non-superuser hits GET/PATCH/DELETE /users/{id}."""
        user_id = authenticated_user["user"].id
        response = await test_client.request(
            method,
            f"/api/v1/users/{user_id}",
            headers=authenticated_user["headers"],
            json={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGetMe:
    """Tests for GET /users/me."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_returns_current_user(
        self, test_client: AsyncClient, authenticated_user: dict
    ):
        """Return the authenticated user without exposing the password hash."""
        response = await test_client.get(
            "/api/v1/users/me", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_200_OK
        assert_user_payload(response.json(), authenticated_user["user"])

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_inactive_user(self, test_client: AsyncClient, create_user):
        """Return 401 when the token belongs to an inactive user."""
        user = await create_user(is_active=False)
        headers = await issue_auth_headers(user)

        response = await test_client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPatchMe:
    """Tests for PATCH /users/me (safe update: privilege flags are ignored)."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_updates_email_and_clears_verification(
        self, test_client: AsyncClient, authenticated_user: dict
    ):
        """Change email and mark the account unverified."""
        response = await test_client.patch(
            "/api/v1/users/me",
            headers=authenticated_user["headers"],
            json={"email": NEW_EMAIL},
        )

        assert response.status_code == status.HTTP_200_OK
        assert_user_payload(
            response.json(),
            authenticated_user["user"],
            email=NEW_EMAIL,
            is_verified=False,
        )

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_duplicate_email(
        self, test_client: AsyncClient, authenticated_user: dict, create_user
    ):
        """Return 400 when the new email already belongs to another user."""
        other = await create_user(email="taken@example.com")

        response = await test_client.patch(
            "/api/v1/users/me",
            headers=authenticated_user["headers"],
            json={"email": other.email},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS

    @pytest.mark.parametrize(
        "password, reason_fragment",
        [
            ("Ab1!", "Password should be at least 8 characters."),
            (
                "lowercase1!",
                "Password should contain at least one uppercase letter.",
            ),
            (
                "NoSpecial1",
                "Password should contain at least one special character.",
            ),
        ],
    )
    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_invalid_password(
        self,
        test_client: AsyncClient,
        authenticated_user: dict,
        password: str,
        reason_fragment: str,
    ):
        """Return 400 when the new password fails UserManager rules."""
        response = await test_client.patch(
            "/api/v1/users/me",
            headers=authenticated_user["headers"],
            json={"password": password},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = response.json()["detail"]
        assert detail["code"] == ErrorCode.UPDATE_USER_INVALID_PASSWORD
        assert reason_fragment in detail["reason"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_updates_password(
        self, test_client: AsyncClient, db_session, authenticated_user: dict
    ):
        """Accept a valid new password and persist a hash that only it verifies against.

        There's no password-login route to re-authenticate through anymore
        (passwordless OTP is the only login flow — see docs/auth.md), so this
        checks the stored hash directly instead of round-tripping via login.
        """
        user_id = authenticated_user["user"].id

        response = await test_client.patch(
            "/api/v1/users/me",
            headers=authenticated_user["headers"],
            json={"password": NEW_PASSWORD},
        )
        assert response.status_code == status.HTTP_200_OK

        result = await db_session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        password_helper = PasswordHelper()
        assert password_helper.verify_and_update(NEW_PASSWORD, user.hashed_password)[0]
        assert not password_helper.verify_and_update(
            DEFAULT_USER_PASSWORD, user.hashed_password
        )[0]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_cannot_escalate_to_superuser(
        self, test_client: AsyncClient, authenticated_user: dict
    ):
        """Ignore is_superuser on PATCH /me (safe=True)."""
        response = await test_client.patch(
            "/api/v1/users/me",
            headers=authenticated_user["headers"],
            json={"is_superuser": True, "is_verified": False, "is_active": False},
        )

        assert response.status_code == status.HTTP_200_OK
        assert_user_payload(response.json(), authenticated_user["user"])


class TestGetUserById:
    """Tests for GET /users/{id} (superuser only)."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_superuser_can_fetch_another_user(
        self,
        test_client: AsyncClient,
        authenticated_superuser: dict,
        create_user,
    ):
        """Return the target user when the caller is a superuser."""
        target = await create_user(email="target@example.com")

        response = await test_client.get(
            f"/api/v1/users/{target.id}",
            headers=authenticated_superuser["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert_user_payload(response.json(), target)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_unknown_id_returns_404(
        self, test_client: AsyncClient, authenticated_superuser: dict
    ):
        """Return 404 when the UUID does not match a user."""
        response = await test_client.get(
            f"/api/v1/users/{MISSING_USER_ID}",
            headers=authenticated_superuser["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_id_returns_404(
        self, test_client: AsyncClient, authenticated_superuser: dict
    ):
        """Return 404 when the path id is not a valid UUID."""
        response = await test_client.get(
            "/api/v1/users/not-a-uuid",
            headers=authenticated_superuser["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPatchUserById:
    """Tests for PATCH /users/{id} (superuser, unsafe update)."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_superuser_can_promote_and_deactivate(
        self,
        test_client: AsyncClient,
        authenticated_superuser: dict,
        create_user,
    ):
        """Allow privilege flags that PATCH /me would ignore."""
        target = await create_user(email="target@example.com")

        response = await test_client.patch(
            f"/api/v1/users/{target.id}",
            headers=authenticated_superuser["headers"],
            json={"is_superuser": True, "is_active": False},
        )

        assert response.status_code == status.HTTP_200_OK
        assert_user_payload(
            response.json(),
            target,
            is_superuser=True,
            is_active=False,
        )

    @pytest.mark.asyncio(loop_scope="function")
    async def test_rejects_duplicate_email(
        self,
        test_client: AsyncClient,
        authenticated_superuser: dict,
        create_user,
    ):
        """Return 400 when assigning an email that already exists."""
        target = await create_user(email="target@example.com")
        other = await create_user(email="taken@example.com")

        response = await test_client.patch(
            f"/api/v1/users/{target.id}",
            headers=authenticated_superuser["headers"],
            json={"email": other.email},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS

    @pytest.mark.asyncio(loop_scope="function")
    async def test_unknown_id_returns_404(
        self, test_client: AsyncClient, authenticated_superuser: dict
    ):
        """Return 404 when patching a user that does not exist."""
        response = await test_client.patch(
            f"/api/v1/users/{MISSING_USER_ID}",
            headers=authenticated_superuser["headers"],
            json={"email": NEW_EMAIL},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteUser:
    """Tests for DELETE /users/{id} (superuser only)."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_superuser_deletes_user_and_items(
        self,
        test_client: AsyncClient,
        authenticated_superuser: dict,
        create_user,
        db_session,
    ):
        """Remove the user and cascade-delete their items."""
        target = await create_user(email="target@example.com")
        db_session.add(
            Item(name="Owned item", description="goes away", user_id=target.id)
        )
        await db_session.commit()

        response = await test_client.delete(
            f"/api/v1/users/{target.id}",
            headers=authenticated_superuser["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert (await db_session.get(User, target.id)) is None
        leftover_items = (
            (await db_session.execute(select(Item).where(Item.user_id == target.id)))
            .scalars()
            .all()
        )
        assert leftover_items == []

    @pytest.mark.asyncio(loop_scope="function")
    async def test_unknown_id_returns_404(
        self, test_client: AsyncClient, authenticated_superuser: dict
    ):
        """Return 404 when deleting a user that does not exist."""
        response = await test_client.delete(
            f"/api/v1/users/{uuid.uuid4()}",
            headers=authenticated_superuser["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
