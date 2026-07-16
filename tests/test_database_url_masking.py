"""Regression tests for connection-string credential disclosure."""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
def test_database_url_mask_preserves_location_without_password():
    from app.utils.config_validator.masking import mask_database_url

    value = "postgresql+psycopg://docuelevate:top-secret@database.internal:5432/docuelevate"
    masked = mask_database_url(value)

    assert masked == "postgresql+psycopg://docuelevate:***@database.internal:5432/docuelevate"
    assert "top-secret" not in masked


@pytest.mark.unit
def test_database_url_mask_handles_sqlite_and_malformed_values():
    from app.utils.config_validator.masking import mask_database_url

    assert mask_database_url("sqlite:////workdir/docuelevate.db") == "sqlite:////workdir/docuelevate.db"
    malformed = "not-a-url-with-a-secret-value"
    masked = mask_database_url(malformed)
    assert masked != malformed
    assert masked.startswith("not-")


@pytest.mark.unit
def test_database_url_is_sensitive_settings_metadata():
    from app.utils.settings_service import SETTING_METADATA

    assert SETTING_METADATA["database_url"]["sensitive"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_database_wizard_never_renders_raw_database_password():
    from app.views.db_wizard import database_wizard

    request = Mock()
    with (
        patch(
            "app.views.db_wizard.settings.database_url",
            "postgresql://docuelevate:top-secret@database.internal/docuelevate",
        ),
        patch("app.views.db_wizard.templates") as templates,
    ):
        await database_wizard(request)

    context = templates.TemplateResponse.call_args.args[1]
    assert context["current_database_url"] == "postgresql://docuelevate:***@database.internal/docuelevate"
    assert "top-secret" not in context["current_database_url"]
