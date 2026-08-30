"""Regression tests for stdlib logs reaching Sentry.

sentry-sdk 2.68 made ``enable_logs`` a no-op and stopped auto-collecting
stdlib records unless ``LoggingIntegration(capture_sentry_logs=True)``.
The app logger must also be at INFO, or ``logger.info`` is dropped before
the SDK's ``callHandlers`` patch runs.
"""

import logging

from app.config import configure_app_logger, logger
from app.sentry import build_logging_integration


def test_app_logger_info_is_enabled() -> None:
    configure_app_logger()

    assert logger.name == "buscaoficio"
    assert logger.getEffectiveLevel() == logging.INFO
    assert logger.isEnabledFor(logging.INFO)


def test_logging_integration_opts_into_sentry_logs() -> None:
    integration = build_logging_integration()

    assert integration.capture_sentry_logs is True
    assert integration._sentry_logs_handler is not None
    assert integration._sentry_logs_handler.level == logging.INFO
    assert integration._breadcrumb_handler is not None
    assert integration._breadcrumb_handler.level == logging.INFO
    assert integration._handler is not None
    assert integration._handler.level == logging.ERROR
