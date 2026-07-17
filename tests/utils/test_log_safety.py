import logging

import pytest

from app.utils.log_safety import restrict_sensitive_provider_logging


@pytest.fixture
def openai_loggers():
    parent = logging.getLogger("openai")
    request_logger = logging.getLogger("openai._base_client")
    previous_levels = (parent.level, request_logger.level)
    yield parent, request_logger
    parent.setLevel(previous_levels[0])
    request_logger.setLevel(previous_levels[1])


@pytest.mark.unit
def test_sensitive_provider_logging_never_includes_debug_prompts(openai_loggers):
    parent, request_logger = openai_loggers
    parent.setLevel(logging.DEBUG)
    request_logger.setLevel(logging.DEBUG)

    restrict_sensitive_provider_logging()

    assert parent.getEffectiveLevel() == logging.WARNING
    assert request_logger.getEffectiveLevel() == logging.WARNING
    assert not request_logger.isEnabledFor(logging.DEBUG)


@pytest.mark.unit
def test_apprise_logging_never_includes_debug_payloads():
    apprise_logger = logging.getLogger("apprise")
    plugin_logger = logging.getLogger("apprise.plugins.pushover")
    previous_levels = (apprise_logger.level, plugin_logger.level)
    try:
        apprise_logger.setLevel(logging.DEBUG)
        plugin_logger.setLevel(logging.NOTSET)

        restrict_sensitive_provider_logging()

        assert apprise_logger.getEffectiveLevel() == logging.WARNING
        assert plugin_logger.getEffectiveLevel() == logging.WARNING
        assert not plugin_logger.isEnabledFor(logging.DEBUG)
    finally:
        apprise_logger.setLevel(previous_levels[0])
        plugin_logger.setLevel(previous_levels[1])
