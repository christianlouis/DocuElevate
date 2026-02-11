"""
Integration tests for external API services using real credentials.

These tests verify that external API integrations work correctly when real
credentials are provided via environment variables (e.g., GitHub Actions secrets).

Each test is guarded by ``pytest.mark.skipif`` so it is skipped automatically
when the required environment variables are absent or still set to placeholder
values.  All tests carry the ``@pytest.mark.requires_external`` marker so they
can be run (or excluded) with::

    pytest -m requires_external          # run only external tests
    pytest -m "not requires_external"    # skip external tests

**Pipeline coverage:**

The tests exercise real end-to-end flows wherever credentials allow:

- *OpenAI*: key validation **and** metadata extraction via chat completion.
- *Azure Document Intelligence*: admin connectivity **and** OCR of a generated PDF.
- *S3*: bucket access, file upload, download verification, and cleanup.
- *Dropbox*: token refresh, file upload, download verification, and cleanup.
- *OneDrive*: token refresh, file upload, download verification, and cleanup.
- *Authentik/OIDC*: discovery endpoint and credential consistency.

Each pipeline test dynamically generates a unique PDF with ``fpdf2`` so every
run operates on fresh data.  Uploaded test files are cleaned up in ``finally``
blocks to avoid polluting external storage.
"""

import json
import logging
import os
import tempfile
import uuid
from typing import Optional

import pytest

from tests.conftest import has_real_env

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test-PDF generator helper
# ---------------------------------------------------------------------------
_TEST_PREFIX = "docuelevate_test_"


def generate_test_pdf(
    content: Optional[str] = None,
    filename_prefix: str = _TEST_PREFIX,
) -> str:
    """Generate a unique test PDF with embedded text.

    Creates a one-page PDF containing *content* (or a random invoice stub)
    and returns the path to the temporary file.  The caller is responsible
    for deleting the file when done.

    Args:
        content: Optional text to embed.  When ``None`` a realistic
                 invoice-style document is generated.
        filename_prefix: Prefix for the temp filename.

    Returns:
        Absolute path to the generated PDF file.
    """
    from fpdf import FPDF

    unique_id = uuid.uuid4().hex[:8]

    if content is None:
        content = (
            f"Invoice #{unique_id}\n"
            f"Date: 2024-06-15\n"
            f"From: Acme Integration Testing GmbH\n"
            f"To: DocuElevate QA Department\n"
            f"Amount: EUR 1,234.56\n\n"
            f"Description: Annual subscription renewal for cloud document\n"
            f"processing services.  Reference: REF-{unique_id}.\n\n"
            f"Payment terms: Net 30 days.\n"
            f"Bank: Deutsche Bank, IBAN: DE89 3704 0044 0532 0130 00\n"
        )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 7, text=content)

    fd, path = tempfile.mkstemp(prefix=filename_prefix, suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("OPENAI_API_KEY"),
    reason="Real OPENAI_API_KEY not available",
)
class TestOpenAIIntegration:
    """Verify OpenAI API connectivity and metadata extraction with real credentials."""

    def test_openai_api_key_is_valid(self, original_env: dict) -> None:
        """Validate that the configured OpenAI API key can list models."""
        import openai

        api_key = original_env["OPENAI_API_KEY"]
        base_url = original_env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        oai = openai.OpenAI(api_key=api_key, base_url=base_url)
        models = oai.models.list()

        assert hasattr(models, "data"), "Expected models response to have 'data' attribute"
        assert len(models.data) > 0, "Expected at least one model to be available"

    def test_openai_test_endpoint_with_real_key(self, client, original_env: dict, monkeypatch) -> None:
        """Test the /api/openai/test endpoint returns success with a real API key."""
        monkeypatch.setattr("app.config.settings.openai_api_key", original_env["OPENAI_API_KEY"])
        if original_env.get("OPENAI_BASE_URL"):
            monkeypatch.setattr("app.config.settings.openai_base_url", original_env["OPENAI_BASE_URL"])

        response = client.get("/api/openai/test")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success", f"OpenAI test endpoint failed: {data.get('message')}"
        assert data.get("models_available", 0) > 0

    def test_openai_metadata_extraction(self, original_env: dict) -> None:
        """End-to-end: send document text to OpenAI and receive structured metadata."""
        import openai

        api_key = original_env["OPENAI_API_KEY"]
        base_url = original_env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        # Use the same prompt structure as extract_metadata_with_gpt task
        unique_id = uuid.uuid4().hex[:8]
        sample_text = (
            f"Invoice #{unique_id}\n"
            f"Date: 2024-06-15\n"
            f"From: Acme Integration Testing GmbH\n"
            f"To: DocuElevate QA Department\n"
            f"Amount: EUR 1,234.56\n"
        )

        prompt = (
            "You are a specialized document analyzer.  Analyze the given text and return a JSON object with:\n"
            '- "document_type": precise classification (e.g., Invoice, Contract)\n'
            '- "language": ISO 639-1 code\n'
            '- "tags": list of up to 4 keywords\n'
            '- "absender": sender name\n'
            '- "empfaenger": recipient name\n\n'
            f"Text:\n{sample_text}\n\n"
            "Return only valid JSON."
        )

        oai = openai.OpenAI(api_key=api_key, base_url=base_url)
        completion = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an intelligent document classifier."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        content = completion.choices[0].message.content
        assert content, "OpenAI returned empty content"

        # Extract JSON from response (may be wrapped in markdown fences)
        import re

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        assert json_match, f"No JSON found in OpenAI response: {content[:200]}"

        metadata = json.loads(json_match.group())
        assert "document_type" in metadata, "Missing document_type in extracted metadata"
        assert "language" in metadata, "Missing language in extracted metadata"


# ---------------------------------------------------------------------------
# Azure Document Intelligence
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("AZURE_AI_KEY", "AZURE_ENDPOINT"),
    reason="Real AZURE_AI_KEY and AZURE_ENDPOINT not available",
)
class TestAzureDocumentIntelligenceIntegration:
    """Verify Azure Document Intelligence connectivity and OCR with real credentials."""

    def test_azure_admin_client_connects(self, original_env: dict) -> None:
        """Validate that the Azure admin client can list operations."""
        from azure.ai.documentintelligence import DocumentIntelligenceAdministrationClient
        from azure.core.credentials import AzureKeyCredential

        admin_client = DocumentIntelligenceAdministrationClient(
            endpoint=original_env["AZURE_ENDPOINT"],
            credential=AzureKeyCredential(original_env["AZURE_AI_KEY"]),
        )

        operations = list(admin_client.list_operations())
        assert isinstance(operations, list)

    def test_azure_test_endpoint_with_real_credentials(self, client, original_env: dict, monkeypatch) -> None:
        """Test the /api/azure/test endpoint returns success with real credentials."""
        monkeypatch.setattr("app.config.settings.azure_ai_key", original_env["AZURE_AI_KEY"])
        monkeypatch.setattr("app.config.settings.azure_endpoint", original_env["AZURE_ENDPOINT"])
        if original_env.get("AZURE_REGION"):
            monkeypatch.setattr("app.config.settings.azure_region", original_env["AZURE_REGION"])

        response = client.get("/api/azure/test")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success", f"Azure test endpoint failed: {data.get('message')}"

    def test_azure_ocr_on_generated_pdf(self, original_env: dict) -> None:
        """End-to-end: send a generated PDF to Azure and receive OCR text back."""
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeOutputOption
        from azure.core.credentials import AzureKeyCredential

        pdf_path = generate_test_pdf()
        try:
            doc_client = DocumentIntelligenceClient(
                endpoint=original_env["AZURE_ENDPOINT"],
                credential=AzureKeyCredential(original_env["AZURE_AI_KEY"]),
            )

            with open(pdf_path, "rb") as f:
                poller = doc_client.begin_analyze_document(
                    "prebuilt-read",
                    body=f,
                    output=[AnalyzeOutputOption.PDF],
                )
            result = poller.result()

            assert result.content, "Azure OCR returned no content"
            assert len(result.content) > 10, f"OCR text too short: {result.content[:50]}"

            # Verify the generated text is recognizable
            assert (
                "Acme" in result.content or "Invoice" in result.content
            ), f"OCR text does not contain expected keywords: {result.content[:200]}"

            # Retrieve the searchable PDF output
            operation_id = poller.details["operation_id"]
            pdf_response = doc_client.get_analyze_result_pdf(
                model_id=result.model_id,
                result_id=operation_id,
            )
            searchable_bytes = b"".join(pdf_response)
            assert len(searchable_bytes) > 0, "Searchable PDF output is empty"
            assert searchable_bytes[:5] == b"%PDF-", "Output is not a valid PDF"
        finally:
            os.unlink(pdf_path)


# ---------------------------------------------------------------------------
# AWS S3 – full upload/download/delete pipeline
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET_NAME"),
    reason="Real AWS credentials and S3_BUCKET_NAME not available",
)
class TestS3Integration:
    """Verify AWS S3 connectivity and upload/download pipeline with real credentials."""

    def test_s3_bucket_accessible(self, original_env: dict) -> None:
        """Validate that the S3 bucket exists and credentials are accepted."""
        import boto3

        s3_client = boto3.client(
            "s3",
            region_name=original_env.get("AWS_REGION", "us-east-1"),
            aws_access_key_id=original_env["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=original_env["AWS_SECRET_ACCESS_KEY"],
        )

        response = s3_client.head_bucket(Bucket=original_env["S3_BUCKET_NAME"])
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_s3_upload_download_delete(self, original_env: dict) -> None:
        """End-to-end: upload a generated PDF to S3, download and verify, then delete."""
        import boto3

        pdf_path = generate_test_pdf()
        s3_key = None
        try:
            s3_client = boto3.client(
                "s3",
                region_name=original_env.get("AWS_REGION", "us-east-1"),
                aws_access_key_id=original_env["AWS_ACCESS_KEY_ID"],
                aws_secret_access_key=original_env["AWS_SECRET_ACCESS_KEY"],
            )
            bucket = original_env["S3_BUCKET_NAME"]
            prefix = original_env.get("S3_FOLDER_PREFIX", "")
            if prefix and not prefix.endswith("/"):
                prefix += "/"
            s3_key = f"{prefix}{_TEST_PREFIX}{uuid.uuid4().hex[:8]}.pdf"

            # Upload
            s3_client.upload_file(pdf_path, bucket, s3_key)

            # Download and verify
            download_path = pdf_path + ".downloaded"
            s3_client.download_file(bucket, s3_key, download_path)

            with open(pdf_path, "rb") as orig, open(download_path, "rb") as dl:
                assert orig.read() == dl.read(), "Downloaded file does not match uploaded file"

            os.unlink(download_path)
        finally:
            os.unlink(pdf_path)
            # Cleanup: delete the test object from S3
            if s3_key:
                try:
                    s3_client.delete_object(Bucket=bucket, Key=s3_key)
                except Exception as exc:
                    logger.warning(f"Failed to clean up S3 test object {s3_key}: {exc}")


# ---------------------------------------------------------------------------
# Dropbox – full upload/download/delete pipeline
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"),
    reason="Real Dropbox credentials not available",
)
class TestDropboxIntegration:
    """Verify Dropbox token validity and upload/download pipeline with real credentials."""

    def test_dropbox_token_refresh_and_account_info(self, original_env: dict) -> None:
        """Validate token refresh and account info retrieval in one go."""
        import dropbox as dbx_lib

        dbx = dbx_lib.Dropbox(
            app_key=original_env["DROPBOX_APP_KEY"],
            app_secret=original_env["DROPBOX_APP_SECRET"],
            oauth2_refresh_token=original_env["DROPBOX_REFRESH_TOKEN"],
        )
        account = dbx.users_get_current_account()
        assert account.email, "Dropbox account missing email"

    def test_dropbox_upload_download_delete(self, original_env: dict) -> None:
        """End-to-end: upload a generated PDF to Dropbox, download it, then delete it."""
        import dropbox as dbx_lib

        pdf_path = generate_test_pdf()
        remote_path = f"/{_TEST_PREFIX}{uuid.uuid4().hex[:8]}.pdf"
        dbx = None
        try:
            dbx = dbx_lib.Dropbox(
                app_key=original_env["DROPBOX_APP_KEY"],
                app_secret=original_env["DROPBOX_APP_SECRET"],
                oauth2_refresh_token=original_env["DROPBOX_REFRESH_TOKEN"],
            )

            # Upload
            with open(pdf_path, "rb") as f:
                dbx.files_upload(
                    f.read(),
                    remote_path,
                    mode=dbx_lib.files.WriteMode.overwrite,
                )

            # Download and verify
            _, response = dbx.files_download(remote_path)
            downloaded = response.content
            with open(pdf_path, "rb") as f:
                assert f.read() == downloaded, "Downloaded Dropbox file does not match uploaded file"
        finally:
            os.unlink(pdf_path)
            # Cleanup
            if dbx:
                try:
                    dbx.files_delete_v2(remote_path)
                except Exception as exc:
                    logger.warning(f"Failed to clean up Dropbox test file {remote_path}: {exc}")


# ---------------------------------------------------------------------------
# OneDrive – full upload/download/delete pipeline
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("ONEDRIVE_CLIENT_ID", "ONEDRIVE_CLIENT_SECRET", "ONEDRIVE_REFRESH_TOKEN"),
    reason="Real OneDrive credentials not available",
)
class TestOneDriveIntegration:
    """Verify OneDrive token validity and upload/download pipeline with real credentials."""

    @staticmethod
    def _get_access_token(env: dict) -> str:
        """Obtain a fresh OneDrive access token via MSAL."""
        import msal

        tenant = env.get("ONEDRIVE_TENANT_ID") or "common"
        app = msal.ConfidentialClientApplication(
            client_id=env["ONEDRIVE_CLIENT_ID"],
            client_credential=env["ONEDRIVE_CLIENT_SECRET"],
            authority=f"https://login.microsoftonline.com/{tenant}",
        )
        result = app.acquire_token_by_refresh_token(
            refresh_token=env["ONEDRIVE_REFRESH_TOKEN"],
            scopes=["https://graph.microsoft.com/.default"],
        )
        assert "access_token" in result, f"OneDrive token acquisition failed: {result.get('error_description')}"
        return result["access_token"]

    def test_onedrive_token_refresh_and_user_info(self, original_env: dict) -> None:
        """Validate token refresh and user info retrieval."""
        import requests

        token = self._get_access_token(original_env)
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert resp.status_code == 200, f"OneDrive user info failed: {resp.text}"

    def test_onedrive_upload_download_delete(self, original_env: dict) -> None:
        """End-to-end: upload a generated PDF to OneDrive, download it, then delete it."""
        import requests

        pdf_path = generate_test_pdf()
        filename = f"{_TEST_PREFIX}{uuid.uuid4().hex[:8]}.pdf"
        folder = original_env.get("ONEDRIVE_FOLDER_PATH", "").strip("/")
        item_id = None
        token = None
        try:
            token = self._get_access_token(original_env)
            headers = {"Authorization": f"Bearer {token}"}

            # Upload (simple upload for small files)
            if folder:
                upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder}/{filename}:/content"
            else:
                upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{filename}:/content"

            with open(pdf_path, "rb") as f:
                upload_resp = requests.put(
                    upload_url,
                    headers={**headers, "Content-Type": "application/pdf"},
                    data=f.read(),
                    timeout=60,
                )
            assert upload_resp.status_code in (200, 201), f"OneDrive upload failed: {upload_resp.text}"
            item_id = upload_resp.json().get("id")

            # Download and verify
            download_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content"
            dl_resp = requests.get(download_url, headers=headers, timeout=60)
            assert dl_resp.status_code == 200, f"OneDrive download failed: {dl_resp.status_code}"

            with open(pdf_path, "rb") as f:
                assert f.read() == dl_resp.content, "Downloaded OneDrive file does not match uploaded file"
        finally:
            os.unlink(pdf_path)
            # Cleanup
            if item_id and token:
                try:
                    requests.delete(
                        f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to clean up OneDrive test file {filename}: {exc}")


# ---------------------------------------------------------------------------
# Authentik / OpenID Connect – discovery endpoint validation
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("AUTHENTIK_CONFIG_URL"),
    reason="Real AUTHENTIK_CONFIG_URL not available",
)
class TestAuthentikIntegration:
    """Verify Authentik / OpenID Connect discovery endpoint is reachable."""

    def test_oidc_discovery_endpoint(self, original_env: dict) -> None:
        """Validate that the OIDC discovery URL returns a valid JSON document."""
        import requests

        config_url = original_env["AUTHENTIK_CONFIG_URL"]
        response = requests.get(config_url, timeout=30)

        assert response.status_code == 200, f"OIDC discovery failed: {response.status_code}"
        data = response.json()

        assert "issuer" in data, "OIDC response missing 'issuer'"
        assert "authorization_endpoint" in data, "OIDC response missing 'authorization_endpoint'"
        assert "token_endpoint" in data, "OIDC response missing 'token_endpoint'"

    def test_authentik_client_credentials_present(self, original_env: dict) -> None:
        """Validate that Authentik client credentials are configured alongside the config URL."""
        client_id = original_env.get("AUTHENTIK_CLIENT_ID")
        client_secret = original_env.get("AUTHENTIK_CLIENT_SECRET")

        if client_id and client_secret:
            assert len(client_id) > 0, "AUTHENTIK_CLIENT_ID should not be empty"
            assert len(client_secret) > 0, "AUTHENTIK_CLIENT_SECRET should not be empty"
        else:
            pytest.skip("AUTHENTIK_CLIENT_ID and/or AUTHENTIK_CLIENT_SECRET not set")


# ---------------------------------------------------------------------------
# Full pipeline: Azure OCR → OpenAI metadata extraction (end-to-end)
# ---------------------------------------------------------------------------
@pytest.mark.requires_external
@pytest.mark.skipif(
    not has_real_env("AZURE_AI_KEY", "AZURE_ENDPOINT", "OPENAI_API_KEY"),
    reason="Real Azure + OpenAI credentials required for full pipeline test",
)
class TestFullOCRMetadataPipeline:
    """End-to-end pipeline: generate PDF → Azure OCR → OpenAI metadata extraction.

    This replicates the core DocuElevate processing flow without requiring
    Celery or Redis, by calling the service APIs directly.
    """

    def test_ocr_then_metadata_extraction(self, original_env: dict) -> None:
        """Generate a PDF, OCR it with Azure, then extract metadata with OpenAI."""
        import re

        import openai
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeOutputOption
        from azure.core.credentials import AzureKeyCredential

        pdf_path = generate_test_pdf()
        try:
            # --- Step 1: Azure OCR ---
            doc_client = DocumentIntelligenceClient(
                endpoint=original_env["AZURE_ENDPOINT"],
                credential=AzureKeyCredential(original_env["AZURE_AI_KEY"]),
            )

            with open(pdf_path, "rb") as f:
                poller = doc_client.begin_analyze_document(
                    "prebuilt-read",
                    body=f,
                    output=[AnalyzeOutputOption.PDF],
                )
            result = poller.result()
            extracted_text = result.content
            assert extracted_text and len(extracted_text) > 10, "OCR produced insufficient text"

            # --- Step 2: OpenAI metadata extraction ---
            api_key = original_env["OPENAI_API_KEY"]
            base_url = original_env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            oai = openai.OpenAI(api_key=api_key, base_url=base_url)

            prompt = (
                "You are a specialized document analyzer.  Analyze the following OCR-extracted text "
                "and return a JSON object with these fields:\n"
                '- "document_type": classification (e.g. Invoice, Contract, Letter)\n'
                '- "language": ISO 639-1 code\n'
                '- "absender": sender\n'
                '- "empfaenger": recipient\n'
                '- "tags": up to 4 keywords\n'
                '- "confidence_score": 0-100\n\n'
                f"OCR text:\n{extracted_text}\n\n"
                "Return only valid JSON."
            )

            completion = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an intelligent document classifier."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )

            content = completion.choices[0].message.content
            assert content, "OpenAI returned empty response"

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            assert json_match, f"No JSON found in response: {content[:200]}"

            metadata = json.loads(json_match.group())

            # Validate key metadata fields
            assert "document_type" in metadata, "Missing document_type"
            assert "language" in metadata, "Missing language"
            assert "absender" in metadata, "Missing absender"
            assert "empfaenger" in metadata, "Missing empfaenger"

            # The generated invoice should be classified reasonably
            doc_type = metadata["document_type"].lower()
            assert any(
                kw in doc_type for kw in ("invoice", "rechnung", "bill")
            ), f"Unexpected document_type: {metadata['document_type']}"
        finally:
            os.unlink(pdf_path)


# ---------------------------------------------------------------------------
# Configuration: verify that Settings correctly loads external env vars
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExternalEnvVarConfiguration:
    """Verify that the Settings class correctly reads external API environment variables.

    These tests do NOT call external APIs; they only validate that the configuration
    layer correctly maps environment variables to Settings fields.
    """

    @staticmethod
    def test_settings_reads_openai_base_url() -> None:
        """Test that OPENAI_BASE_URL is correctly loaded into Settings."""
        from app.config import Settings

        custom_url = "https://custom-openai.example.com/v1"
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            openai_base_url=custom_url,
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.openai_base_url == custom_url

    @staticmethod
    def test_settings_reads_s3_configuration() -> None:
        """Test that S3-related settings are correctly loaded."""
        from app.config import Settings

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            aws_access_key_id="AKIAEXAMPLE",
            aws_secret_access_key="secretkey",
            s3_bucket_name="my-bucket",
            s3_folder_prefix="uploads/",
        )
        assert config.aws_access_key_id == "AKIAEXAMPLE"
        assert config.aws_secret_access_key == "secretkey"
        assert config.s3_bucket_name == "my-bucket"
        assert config.s3_folder_prefix == "uploads/"

    @staticmethod
    def test_settings_reads_onedrive_configuration() -> None:
        """Test that OneDrive-related settings are correctly loaded."""
        from app.config import Settings

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            onedrive_client_id="client-123",
            onedrive_client_secret="secret-456",
            onedrive_tenant_id="tenant-789",
            onedrive_refresh_token="refresh-abc",
            onedrive_folder_path="Documents/Test",
        )
        assert config.onedrive_client_id == "client-123"
        assert config.onedrive_client_secret == "secret-456"
        assert config.onedrive_tenant_id == "tenant-789"
        assert config.onedrive_refresh_token == "refresh-abc"
        assert config.onedrive_folder_path == "Documents/Test"

    @staticmethod
    def test_settings_reads_dropbox_configuration() -> None:
        """Test that Dropbox-related settings are correctly loaded."""
        from app.config import Settings

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            dropbox_app_key="dbx-key",
            dropbox_app_secret="dbx-secret",
            dropbox_refresh_token="dbx-refresh",
        )
        assert config.dropbox_app_key == "dbx-key"
        assert config.dropbox_app_secret == "dbx-secret"
        assert config.dropbox_refresh_token == "dbx-refresh"

    @staticmethod
    def test_settings_reads_authentik_configuration() -> None:
        """Test that Authentik/OIDC settings are correctly loaded."""
        from app.config import Settings

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            authentik_client_id="auth-client",
            authentik_client_secret="auth-secret",
            authentik_config_url="https://auth.example.com/.well-known/openid-configuration",
        )
        assert config.authentik_client_id == "auth-client"
        assert config.authentik_client_secret == "auth-secret"
        assert config.authentik_config_url == "https://auth.example.com/.well-known/openid-configuration"

    @staticmethod
    def test_settings_optional_services_default_to_none() -> None:
        """Test that optional external service settings default to None when not provided."""
        from app.config import Settings

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.aws_access_key_id is None
        assert config.aws_secret_access_key is None
        assert config.s3_bucket_name is None
        assert config.onedrive_client_id is None
        assert config.onedrive_client_secret is None
        assert config.onedrive_refresh_token is None
        assert config.dropbox_app_key is None
        assert config.dropbox_app_secret is None
        assert config.dropbox_refresh_token is None
        assert config.authentik_client_id is None
        assert config.authentik_client_secret is None
        assert config.authentik_config_url is None


# ---------------------------------------------------------------------------
# Test-PDF generator unit tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPdfGenerator:
    """Verify that the test PDF generator produces valid PDFs with extractable text."""

    @staticmethod
    def test_generate_default_pdf() -> None:
        """Test that generate_test_pdf creates a valid PDF with embedded text."""
        import PyPDF2

        path = generate_test_pdf()
        try:
            assert os.path.exists(path)
            assert os.path.getsize(path) > 100

            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                assert len(reader.pages) >= 1
                text = reader.pages[0].extract_text()
                assert "Invoice" in text
                assert "Acme" in text
        finally:
            os.unlink(path)

    @staticmethod
    def test_generate_custom_content_pdf() -> None:
        """Test that generate_test_pdf accepts custom content."""
        import PyPDF2

        custom = "Custom test content for verification"
        path = generate_test_pdf(content=custom)
        try:
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = reader.pages[0].extract_text()
                assert "Custom test content" in text
        finally:
            os.unlink(path)

    @staticmethod
    def test_generated_pdfs_are_unique() -> None:
        """Test that consecutive calls produce different PDFs."""
        path1 = generate_test_pdf()
        path2 = generate_test_pdf()
        try:
            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                assert f1.read() != f2.read(), "Two generated PDFs should differ"
        finally:
            os.unlink(path1)
            os.unlink(path2)
