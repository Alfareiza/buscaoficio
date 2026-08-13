"""Tests for FastAPI-served static assets used by FastAdmin branding."""

import pytest
from fastapi import status


class TestAdminLogo:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_header_logo_is_served(self, test_client):
        """Serve the BuscaOficio logo at the FastAdmin header/sign-in URL."""
        response = await test_client.get(
            "/static/images/logo/busca-oficio-logo-principal.svg"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "image/svg" in response.headers["content-type"]
        assert b"<svg" in response.content
