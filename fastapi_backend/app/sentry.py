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


def build_logging_integration() -> LoggingIntegration:
    """Bridge stdlib logging into Sentry without depending on a root handler.

    sentry-sdk 2.68+ patches ``Logger.callHandlers`` (it does not install a
    handler uvicorn's ``dictConfig`` could strip). ``enable_logs`` is a no-op
    in that release; stdlib → Sentry Logs requires ``capture_sentry_logs``.
    """
    return LoggingIntegration(
        sentry_logs_level=logging.INFO,
        level=logging.INFO,
        event_level=logging.ERROR,
        capture_sentry_logs=True,
    )


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
        integrations=[build_logging_integration()],
    )
    # fastapi-cli re-logs an import-time failure as logger.error before
    # re-raising it, which would open a second, stack-trace-less issue for
    # the same crash.
    ignore_logger("fastapi_cli.discover")
