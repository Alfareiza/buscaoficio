from fastapi.routing import APIRoute
from app.main import app
from app.utils import simple_generate_unique_route_id


def test_simple_generate_unique_route_id(mocker):
    mock_route = mocker.Mock(spec=APIRoute)

    mock_route.tags = ["auth"]
    mock_route.name = "authenticate_user"

    unique_id = simple_generate_unique_route_id(mock_route)

    assert unique_id == "auth-authenticate_user"


def test_all_api_routes_have_openapi_docs():
    missing = [
        f"{sorted(route.methods)} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and (not route.summary or not route.description)
    ]

    assert missing == [], f"Routes missing OpenAPI docs: {missing}"
