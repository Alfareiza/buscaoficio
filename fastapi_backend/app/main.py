import logging
import sys

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from fastadmin import fastapi_app as admin_app
from sentry_sdk.integrations.logging import LoggingIntegration

from app.routes.auth import router as auth_router
from app.routes.items import router as items_router
from app.routes.users import router as users_router

from . import admin  # noqa: F401
from .config import STATIC_DIR, logger, settings
from .users import AUTH_URL_PATH
from .utils import simple_generate_unique_route_id

if settings.SENTRY_DSN and "pytest" not in sys.modules:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or "development",
        send_default_pii=False,
        traces_sample_rate=(
            0.1 if settings.SENTRY_ENVIRONMENT == "production" else 1.0
        ),
        enable_logs=True,
        integrations=[
            LoggingIntegration(
                sentry_logs_level=logging.INFO,
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
    )
    logger.info("Sentry initialized")

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

app.include_router(auth_router, prefix=f"/{AUTH_URL_PATH}")
app.include_router(users_router, prefix="/users")
app.include_router(items_router, prefix="/items")

add_pagination(app)
