import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from fastadmin import fastapi_app as admin_app

from app.routes.auth import router as auth_router
from app.routes.items import router as items_router
from app.routes.users import router as users_router

from . import admin  # noqa: F401
from .config import STATIC_DIR, settings
from .users import API_V1_PREFIX, AUTH_URL_PATH
from .utils import simple_generate_unique_route_id

# Sentry is initialized in app/__init__.py, before app.config builds
# Settings() — see app/sentry.py for why it cannot live here.

app = FastAPI(
    generate_unique_id_function=simple_generate_unique_route_id,
    openapi_url=settings.OPENAPI_URL,
)

app.mount("/admin", admin_app)
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

# Middleware for CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette's default handler for an uncaught exception returns a plain-
    # text "Internal Server Error" body. The frontend's error parsing only
    # recognizes JSON {"detail": ...} (the shape FastAPI's own HTTPException
    # produces), so a plain-text 500 was falling through to a generic message
    # with no Sentry event at all. capture_exception here is explicit rather
    # than relying on Sentry's auto-instrumentation timing relative to this
    # handler.
    sentry_sdk.capture_exception(exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.include_router(auth_router, prefix=f"{API_V1_PREFIX}/{AUTH_URL_PATH}")
app.include_router(users_router, prefix=f"{API_V1_PREFIX}/users")
app.include_router(items_router, prefix=f"{API_V1_PREFIX}/items")

add_pagination(app)
