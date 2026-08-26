"""Sentry bootstrap.

Reads os.environ directly instead of app.config.Settings, and is called from
app/__init__.py, so the SDK is already live by the time app.config builds
Settings(). That call raises on a missing or malformed env var, at import
time, and an init wired up any later would never get to report it.
"""

import logging
import os
import sys

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger


def init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn or "pytest" in sys.modules:
        return

    environment = os.environ.get("SENTRY_ENVIRONMENT") or "development"
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        traces_sample_rate=0.1 if environment == "production" else 1.0,
        enable_logs=True,
        integrations=[
            LoggingIntegration(
                sentry_logs_level=logging.INFO,
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
    )
    # fastapi-cli re-logs an import-time failure as logger.error before
    # re-raising it, which would open a second, stack-trace-less issue for
    # the same crash.
    ignore_logger("fastapi_cli.discover")
