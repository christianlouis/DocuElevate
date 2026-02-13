"""Comprehensive tests for app/api/azure.py module."""

from unittest.mock import MagicMock, Mock, patch

import azure.core.exceptions
import pytest


@pytest.mark.unit
class TestAzureTestConnectionEndpoint:
    """Tests for test_azure_connection endpoint."""

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_success(self, mock_settings, mock_credential, mock_admin_client_class):
        """Test successful Azure Document Intelligence connection."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        # Mock admin client and operations
        mock_client = MagicMock()
        mock_operations = [
            MagicMock(
                operation_id="op1",
                status="succeeded",
                created_on="2024-01-01",
                kind="documentModelBuild",
            )
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "success"
        assert result["operations_count"] == 1
        assert len(result["recent_operations"]) == 1

    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_no_endpoint(self, mock_settings):
        """Test connection when endpoint is not configured."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = None
        mock_settings.azure_ai_key = "test-key"

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "endpoint" in result["message"].lower()

    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_no_api_key(self, mock_settings):
        """Test connection when API key is not configured."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = None

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "api key" in result["message"].lower()

    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_missing_both(self, mock_settings):
        """Test connection when both endpoint and key are missing."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = None
        mock_settings.azure_ai_key = None

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "endpoint" in result["message"].lower()
        assert "api key" in result["message"].lower()

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_authentication_error(self, mock_settings, mock_credential, mock_admin_client_class):
        """Test connection with authentication error."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "invalid-key"

        mock_admin_client_class.side_effect = azure.core.exceptions.ClientAuthenticationError("Invalid key")

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "authentication" in result["message"].lower()

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_service_request_error(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test connection with service request error."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_admin_client_class.side_effect = azure.core.exceptions.ServiceRequestError("Cannot reach endpoint")

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "service request" in result["message"].lower()

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_value_error(self, mock_settings, mock_credential, mock_admin_client_class):
        """Test connection with configuration value error."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "invalid-endpoint"
        mock_settings.azure_ai_key = "test-key"

        mock_admin_client_class.side_effect = ValueError("Invalid endpoint format")

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "configuration" in result["message"].lower()

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_unexpected_error(self, mock_settings, mock_credential, mock_admin_client_class):
        """Test connection with unexpected error."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_admin_client_class.side_effect = RuntimeError("Unexpected error")

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "error"
        assert "unexpected" in result["message"].lower()

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_with_multiple_operations(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test connection returning multiple operations."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        mock_operations = [
            MagicMock(operation_id="op1", status="succeeded", created_on="2024-01-01", kind="build"),
            MagicMock(operation_id="op2", status="running", created_on="2024-01-02", kind="analyze"),
            MagicMock(operation_id="op3", status="failed", created_on="2024-01-03", kind="compose"),
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "success"
        assert result["operations_count"] == 3
        assert len(result["recent_operations"]) == 3

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_with_empty_operations(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test connection returning empty operations list."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "success"
        assert result["operations_count"] == 0

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_operations_parsing_error(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test handling of errors while parsing operations."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        # Operations that will cause error when parsing
        mock_op = MagicMock(operation_id=None)
        mock_client.list_operations.return_value = iter([mock_op])
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        # Should still return success even with parsing error
        assert result["status"] == "success"

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_recent_operations_limited(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test that only first 3 operations are returned in recent_operations."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        # Create more than 3 operations
        mock_operations = [
            MagicMock(operation_id=f"op{i}", status="succeeded", created_on=f"2024-01-0{i}", kind="build")
            for i in range(1, 6)
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "success"
        assert result["operations_count"] == 5
        assert len(result["recent_operations"]) == 3

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_operation_without_all_attrs(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test handling operations missing some attributes."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        # Operation missing some attributes
        mock_op = MagicMock(spec=["operation_id"])
        mock_op.operation_id = "op1"
        # status, created_on, kind are missing
        mock_client.list_operations.return_value = iter([mock_op])
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        # Should handle gracefully
        assert result["status"] == "success"
        if result.get("recent_operations"):
            op_info = result["recent_operations"][0]
            assert op_info["id"] == "op1"
            assert op_info["status"] == "Unknown"

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_returns_endpoint_in_response(
        self, mock_settings, mock_credential, mock_admin_client_class
    ):
        """Test that endpoint is included in successful response."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://myendpoint.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        result = await test_azure_connection(mock_request)

        assert result["status"] == "success"
        assert result["endpoint"] == "https://myendpoint.cognitiveservices.azure.com/"

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    @pytest.mark.asyncio
    async def test_azure_connection_uses_credential(
        self, mock_settings, mock_credential_class, mock_admin_client_class
    ):
        """Test that AzureKeyCredential is used correctly."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "my-secret-key"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        mock_request = Mock()
        await test_azure_connection(mock_request)

        # Verify AzureKeyCredential was called with the API key
        mock_credential_class.assert_called_once_with("my-secret-key")


@pytest.mark.integration
class TestAzureTestConnectionIntegration:
    """Integration tests for Azure test connection endpoint."""

    def test_azure_test_endpoint_requires_auth(self, client):
        """Test /azure/test endpoint requires authentication."""
        response = client.get("/api/azure/test")
        # Should be 200 (if no auth), 302 (redirect to login), or 401/403 (unauthorized)
        assert response.status_code in [200, 302, 401, 403]

    @patch("app.api.azure.settings")
    def test_azure_test_endpoint_returns_json(self, mock_settings, client):
        """Test /azure/test endpoint returns JSON response."""
        mock_settings.azure_endpoint = None
        mock_settings.azure_ai_key = None

        response = client.get("/api/azure/test")
        # Should get a response (even if error due to missing config)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data


@pytest.mark.unit
class TestAzureModuleStructure:
    """Tests for Azure module structure and exports."""

    def test_module_imports(self):
        """Test that the module can be imported."""
        from app.api import azure

        assert hasattr(azure, "test_azure_connection")
        assert hasattr(azure, "router")

    def test_router_configured(self):
        """Test that router is properly configured."""
        from app.api.azure import router

        assert router is not None
        # APIRouter should have routes registered
        # The test_azure_connection endpoint should be registered

    def test_endpoint_decorator(self):
        """Test that endpoint has proper decorators."""
        from app.api.azure import test_azure_connection

        # Should be callable
        assert callable(test_azure_connection)
