from fastapi import Request
from fastapi.routing import APIRoute


def simple_generate_unique_route_id(route: APIRoute):
    return f"{route.tags[0]}-{route.name}"


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, checking X-Forwarded-For first."""
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
