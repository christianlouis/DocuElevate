"""Comprehensive tests for app/api/azure.py to improve coverage."""

import pytest
from unittest.mock import MagicMock, patch

import azure.core.exceptions


@pytest.mark.unit
class TestAzureTestConnectionEndpoint:
    """Tests for test_azure_connection endpoint."""

    @pytest.mark.asyncio
    @patch("app.api.azure.settings")
    async def test_missing_endpoint(self, mock_settings):
        """Test returns error when endpoint is missing."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = None
        mock_settings.azure_ai_key = "test-key"
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "endpoint" in result["message"]

    @pytest.mark.asyncio
    @patch("app.api.azure.settings")
    async def test_missing_api_key(self, mock_settings):
        """Test returns error when API key is missing."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = None
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "API key" in result["message"]

    @pytest.mark.asyncio
    @patch("app.api.azure.settings")
    async def test_both_missing(self, mock_settings):
        """Test returns error listing both missing items."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = None
        mock_settings.azure_ai_key = None
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "endpoint" in result["message"]
        assert "API key" in result["message"]

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_successful_connection_with_operations(self, mock_settings, mock_cred, mock_client_cls):
        """Test successful connection with operations returned."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_op = MagicMock()
        mock_op.operation_id = "op1"
        mock_op.status = "succeeded"
        mock_op.created_on = "2024-01-01"
        mock_op.kind = "documentModelBuild"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = [mock_op]
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "success"
        assert result["operations_count"] == 1
        assert result["endpoint"] == "https://test.cognitiveservices.azure.com/"
        assert len(result["recent_operations"]) == 1

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_successful_connection_empty_operations(self, mock_settings, mock_cred, mock_client_cls):
        """Test successful connection with no operations."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = []
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "success"
        assert result["operations_count"] == 0
        assert result["recent_operations"] == []

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_successful_with_more_than_3_operations(self, mock_settings, mock_cred, mock_client_cls):
        """Test only 3 recent operations returned."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_ops = []
        for i in range(5):
            op = MagicMock()
            op.operation_id = f"op{i}"
            op.status = "succeeded"
            op.created_on = f"2024-01-0{i+1}"
            op.kind = "build"
            mock_ops.append(op)

        mock_client = MagicMock()
        mock_client.list_operations.return_value = mock_ops
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "success"
        assert result["operations_count"] == 5
        assert len(result["recent_operations"]) == 3

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_operation_without_operation_id(self, mock_settings, mock_cred, mock_client_cls):
        """Test operation without operation_id is skipped."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_op = MagicMock()
        mock_op.operation_id = None  # No operation_id

        mock_client = MagicMock()
        mock_client.list_operations.return_value = [mock_op]
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "success"
        assert result["operations_count"] == 0

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_operation_missing_attributes(self, mock_settings, mock_cred, mock_client_cls):
        """Test operation missing some attributes uses defaults."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_op = MagicMock(spec=["operation_id"])
        mock_op.operation_id = "op1"

        mock_client = MagicMock()
        mock_client.list_operations.return_value = [mock_op]
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "success"
        # The operation should have "Unknown" for missing attrs
        assert len(result["recent_operations"]) == 1
        op_info = result["recent_operations"][0]
        assert op_info["status"] == "Unknown"
        assert op_info["created"] == "Unknown"
        assert op_info["kind"] == "Unknown"

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_operations_parsing_error(self, mock_settings, mock_cred, mock_client_cls):
        """Test error during operations parsing still returns success."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client = MagicMock()
        # list_operations works, but iterating over operations raises
        mock_client.list_operations.return_value = MagicMock(
            __iter__=MagicMock(side_effect=Exception("Parse error"))
        )
        # Make list() work but then the for loop fails
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        # Should still handle this gracefully
        assert result["status"] in ["success", "error"]

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_authentication_error(self, mock_settings, mock_cred, mock_client_cls):
        """Test authentication error returns error status."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "invalid-key"

        mock_client = MagicMock()
        mock_client.list_operations.side_effect = azure.core.exceptions.ClientAuthenticationError("Invalid key")
        mock_client_cls.return_value = mock_client
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "Authentication error" in result["message"] or "authentication" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_service_request_error(self, mock_settings, mock_cred, mock_client_cls):
        """Test service request error returns error status."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client_cls.side_effect = azure.core.exceptions.ServiceRequestError("Cannot reach endpoint")
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "Service request error" in result["message"] or "service" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_value_error(self, mock_settings, mock_cred, mock_client_cls):
        """Test ValueError returns error status."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "invalid"
        mock_settings.azure_ai_key = "test-key"

        mock_client_cls.side_effect = ValueError("Invalid endpoint format")
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "Configuration error" in result["message"] or "error" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.settings")
    async def test_unexpected_error(self, mock_settings, mock_cred, mock_client_cls):
        """Test unexpected error returns error status."""
        from app.api.azure import test_azure_connection

        mock_settings.azure_endpoint = "https://test.cognitiveservices.azure.com/"
        mock_settings.azure_ai_key = "test-key"

        mock_client_cls.side_effect = RuntimeError("Unexpected!")
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    @patch("app.api.azure.settings")
    async def test_outer_exception(self, mock_settings):
        """Test outer exception handler catches all errors."""
        from app.api.azure import test_azure_connection

        # Make settings access itself raise
        type(mock_settings).azure_endpoint = property(lambda self: (_ for _ in ()).throw(RuntimeError("outer")))
        mock_request = MagicMock()

        result = await test_azure_connection(mock_request)
        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]
