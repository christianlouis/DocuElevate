from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import openai
import pytest

from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.utils.provider_limits import ProviderRateLimited


@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(message="connection", request=httpx.Request("POST", "https://example.test")),
        openai.APITimeoutError(request=httpx.Request("POST", "https://example.test")),
    ],
)
def test_openai_transport_errors_are_rethrown_for_celery_retry(monkeypatch, tmp_path, error):
    settings = SimpleNamespace(
        workdir=str(tmp_path),
        ai_provider="openai",
        ai_model=None,
        openai_model="gpt-test",
        metadata_max_input_tokens=1000,
    )
    provider = Mock()
    provider.chat_completion.side_effect = error
    with (
        patch("app.tasks.extract_metadata_with_gpt.settings", settings),
        patch("app.tasks.extract_metadata_with_gpt.is_ai_provider_configured", return_value=True),
        patch("app.tasks.extract_metadata_with_gpt.get_ai_provider", return_value=provider),
        patch("app.tasks.extract_metadata_with_gpt.log_task_progress"),
        patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf"),
    ):
        with pytest.raises(type(error)):
            extract_metadata_with_gpt.run("document.pdf", "text")


def test_legacy_azure_ocr_429_preserves_retry_after(tmp_path):
    import importlib

    legacy = importlib.import_module("app.tasks.process_with_azure_document_intelligence")
    workdir = tmp_path
    (workdir / "tmp").mkdir()
    (workdir / "tmp" / "document.bin").write_bytes(b"data")
    error = RuntimeError("rate limited")
    error.status_code = 429
    error.response = SimpleNamespace(headers={"Retry-After": "9"})
    client = Mock()
    client.begin_analyze_document.side_effect = error
    settings = SimpleNamespace(workdir=str(workdir), azure_ai_key="key")

    with (
        patch.object(legacy, "settings", settings),
        patch.object(legacy, "document_intelligence_client", client),
        patch.object(legacy, "log_task_progress"),
    ):
        with pytest.raises(ProviderRateLimited) as caught:
            legacy.process_with_azure_document_intelligence.run("document.bin")
    assert caught.value.retry_after == 9
