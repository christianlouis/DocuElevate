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
@pytest.mark.parametrize(
    ("value", "expected_location"),
    [
        (
            "mysql+pymysql://docuelevate:mysql-secret@mysql.internal:3306/docuelevate",
            "mysql+pymysql://docuelevate:***@mysql.internal:3306/docuelevate",
        ),
        (
            "mariadb+mariadbconnector://docuelevate:maria-secret@maria.internal:3306/archive",
            "mariadb+mariadbconnector://docuelevate:***@maria.internal:3306/archive",
        ),
    ],
)
def test_database_url_mask_supports_sqlalchemy_database_drivers(value, expected_location):
    from app.utils.config_validator.masking import mask_database_url

    assert mask_database_url(value) == expected_location
    assert "secret" not in mask_database_url(value)


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settings_page_context_never_contains_raw_database_password():
    from app.views import settings as settings_view

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    metadata = {"type": "str", "sensitive": True}
    request = Mock()
    request.session = {"user": {"id": "admin", "is_admin": True}}
    with (
        patch.object(settings_view, "get_all_settings_from_db", return_value={"database_url": raw_url}),
        patch.object(settings_view, "get_settings_by_category", return_value={"Core": ["database_url"]}),
        patch.object(settings_view, "get_setting_metadata", return_value=metadata),
        patch.object(settings_view, "templates") as templates,
    ):
        await settings_view.settings_page(request, Mock())

    context = templates.TemplateResponse.call_args.args[1]
    assert "top-secret" not in str(context)
    assert context["settings_data"]["Core"][0]["display_value"] == (
        "postgresql://docuelevate:***@database.internal:5432/docuelevate"
    )


@pytest.mark.unit
def test_settings_api_safe_value_masks_database_and_other_sensitive_values():
    from app.api.settings import _safe_setting_value

    database_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    assert _safe_setting_value("database_url", database_url, {"sensitive": True}) == (
        "postgresql://docuelevate:***@database.internal:5432/docuelevate"
    )
    assert _safe_setting_value("openai_api_key", "sk-secret-value", {"sensitive": True}) != "sk-secret-value"
    assert _safe_setting_value("workdir", "/workdir", {"sensitive": False}) == "/workdir"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settings_api_list_and_single_value_never_return_database_password():
    from app.api import settings as settings_api

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    metadata = {"type": "str", "sensitive": True}
    with (
        patch.object(settings_api, "SETTING_METADATA", {"database_url": metadata}),
        patch.object(settings_api.settings, "database_url", raw_url),
        patch.object(settings_api, "get_all_settings_from_db", return_value={"database_url": raw_url}),
        patch.object(settings_api, "get_setting_metadata", return_value=metadata),
        patch.object(settings_api, "get_settings_by_category", return_value={"Core": ["database_url"]}),
    ):
        listing = await settings_api.get_settings(Mock(), Mock(), {"is_admin": True})
        single = await settings_api.get_setting("database_url", Mock(), Mock(), {"is_admin": True})

    payload = listing.model_dump()
    serialized = str(payload)
    assert "top-secret" not in serialized
    assert payload["settings"]["database_url"]["value"] == (
        "postgresql://docuelevate:***@database.internal:5432/docuelevate"
    )
    assert payload["db_settings"]["database_url"] == ("postgresql://docuelevate:***@database.internal:5432/docuelevate")
    assert single.value == "postgresql://docuelevate:***@database.internal:5432/docuelevate"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settings_update_response_and_export_never_return_database_password():
    from app.api import settings as settings_api

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    metadata = {"type": "str", "sensitive": True, "restart_required": True}
    request = Mock()
    request.session = {"user": {"username": "admin"}}
    with (
        patch.object(settings_api, "get_setting_metadata", return_value=metadata),
        patch.object(settings_api, "validate_setting_value", return_value=(True, None)),
        patch.object(settings_api, "save_setting_to_db", return_value=True),
        patch.object(settings_api, "notify_settings_updated"),
        patch("app.utils.settings_service.get_settings_for_export", return_value={"DATABASE_URL": raw_url}),
    ):
        update = await settings_api.update_setting(
            "database_url",
            settings_api.SettingUpdate(key="database_url", value=raw_url),
            request,
            Mock(),
            {"is_admin": True},
        )
        exported = await settings_api.export_env_settings(request, Mock(), {"is_admin": True})

    assert "top-secret" not in str(update)
    assert update["value"] == "postgresql://docuelevate:***@database.internal:5432/docuelevate"
    assert b"top-secret" not in exported.body
    assert b"DATABASE_URL=postgresql://docuelevate:***@database.internal:5432/docuelevate" in exported.body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settings_bulk_update_response_never_returns_database_password():
    from app.api import settings as settings_api

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    metadata = {"type": "str", "sensitive": True, "restart_required": True}
    request = Mock()
    request.session = {"user": {"username": "admin"}}
    with (
        patch.object(settings_api, "get_setting_metadata", return_value=metadata),
        patch.object(settings_api, "validate_setting_value", return_value=(True, None)),
        patch.object(settings_api, "save_setting_to_db", return_value=True),
        patch.object(settings_api, "notify_settings_updated"),
    ):
        result = await settings_api.bulk_update_settings(
            [settings_api.SettingUpdate(key="database_url", value=raw_url)],
            request,
            Mock(),
            {"is_admin": True},
        )

    assert "top-secret" not in str(result)
    assert result["updated"][0]["value"] == ("postgresql://docuelevate:***@database.internal:5432/docuelevate")


@pytest.mark.unit
def test_diagnostic_settings_dump_never_logs_database_password(caplog):
    from app.utils.config_validator import settings_display

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    with patch.object(settings_display.settings, "database_url", raw_url):
        with caplog.at_level("INFO", logger=settings_display.__name__):
            settings_display.dump_all_settings()

    rendered_logs = caplog.text
    assert "top-secret" not in rendered_logs
    assert "postgresql://docuelevate:***@database.internal:5432/docuelevate" in rendered_logs


@pytest.mark.unit
def test_settings_diagnostic_display_masks_database_password_even_when_values_requested():
    from app.utils.config_validator import settings_display

    raw_url = "postgresql://docuelevate:top-secret@database.internal:5432/docuelevate"
    with patch.object(settings_display.settings, "database_url", raw_url):
        result = settings_display.get_settings_for_display(show_values=True)

    database_entry = next(item for item in result["Core"] if item["name"] == "database_url")
    assert database_entry["value"] == "postgresql://docuelevate:***@database.internal:5432/docuelevate"
    assert "top-secret" not in str(result)
