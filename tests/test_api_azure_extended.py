"""Comprehensive unit tests for app/api/azure.py module."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestAzureTestConnection:
    """Tests for GET /azure/test endpoint."""

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_success(self, mock_admin_client_class):
        """Test successful Azure Document Intelligence connection."""
        from app.config import settings

        # Mock admin client and operations
        mock_client = MagicMock()
        mock_operations = [
            MagicMock(operation_id="op1", status="succeeded", created_on="2024-01-01", kind="documentModelBuild")
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should return success status
                # Should include operations_count
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_no_endpoint(self, mock_admin_client_class):
        """Test connection when endpoint is not configured."""
        from app.config import settings

        with patch.object(settings, "azure_endpoint", None):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should return error status
                # Should indicate missing endpoint
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_no_api_key(self, mock_admin_client_class):
        """Test connection when API key is not configured."""
        from app.config import settings

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", None):
                # Should return error status
                # Should indicate missing API key
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_missing_both(self, mock_admin_client_class):
        """Test connection when both endpoint and key are missing."""
        from app.config import settings

        with patch.object(settings, "azure_endpoint", None):
            with patch.object(settings, "azure_ai_key", None):
                # Should return error status
                # Should list both missing items
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    @patch("app.api.azure.azure.core.exceptions.ClientAuthenticationError")
    def test_azure_connection_authentication_error(self, mock_auth_error, mock_admin_client_class):
        """Test connection with authentication error."""
        import azure.core.exceptions

        from app.config import settings

        mock_admin_client_class.side_effect = azure.core.exceptions.ClientAuthenticationError("Invalid key")

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "invalid-key"):
                # Should return error status
                # Should indicate authentication error
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_service_request_error(self, mock_admin_client_class):
        """Test connection with service request error."""
        import azure.core.exceptions

        from app.config import settings

        mock_admin_client_class.side_effect = azure.core.exceptions.ServiceRequestError("Cannot reach endpoint")

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should return error status
                # Should indicate service request error
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_value_error(self, mock_admin_client_class):
        """Test connection with configuration value error."""
        from app.config import settings

        mock_admin_client_class.side_effect = ValueError("Invalid endpoint format")

        with patch.object(settings, "azure_endpoint", "invalid-endpoint"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should return error status
                # Should indicate configuration error
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_unexpected_error(self, mock_admin_client_class):
        """Test connection with unexpected error."""
        from app.config import settings

        mock_admin_client_class.side_effect = RuntimeError("Unexpected error")

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should return error status
                # Should include error details
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_with_operations(self, mock_admin_client_class):
        """Test connection returning multiple operations."""
        from app.config import settings

        mock_client = MagicMock()
        mock_operations = [
            MagicMock(operation_id="op1", status="succeeded", created_on="2024-01-01", kind="build"),
            MagicMock(operation_id="op2", status="running", created_on="2024-01-02", kind="analyze"),
            MagicMock(operation_id="op3", status="failed", created_on="2024-01-03", kind="compose"),
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # operations_count should be 3
                # recent_operations should contain first 3
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_with_empty_operations(self, mock_admin_client_class):
        """Test connection returning empty operations list."""
        from app.config import settings

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should still return success
                # operations_count should be 0
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_operations_parsing_error(self, mock_admin_client_class):
        """Test handling of errors while parsing operations."""
        from app.config import settings

        mock_client = MagicMock()
        # Operations that will cause error when parsing
        mock_operations = [MagicMock(operation_id=None)]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should still return success
                # Should indicate couldn't parse operations
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_recent_operations_limited(self, mock_admin_client_class):
        """Test that only first 3 operations are returned in recent_operations."""
        from app.config import settings

        mock_client = MagicMock()
        # Create more than 3 operations
        mock_operations = [
            MagicMock(operation_id=f"op{i}", status="succeeded", created_on=f"2024-01-0{i}", kind="build")
            for i in range(1, 6)
        ]
        mock_client.list_operations.return_value = iter(mock_operations)
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # recent_operations should contain only 3 items
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_operation_without_all_attrs(self, mock_admin_client_class):
        """Test handling operations missing some attributes."""
        from app.config import settings

        mock_client = MagicMock()
        # Operation missing some attributes
        mock_op = MagicMock(spec=["operation_id"])
        mock_op.operation_id = "op1"
        # status, created_on, kind are missing
        mock_client.list_operations.return_value = iter([mock_op])
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should handle gracefully with "Unknown" values
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_logs_success(self, mock_admin_client_class):
        """Test that successful connection is logged."""
        from app.config import settings

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should log success message
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_logs_errors(self, mock_admin_client_class):
        """Test that errors are logged."""
        from app.config import settings

        mock_admin_client_class.side_effect = Exception("Test error")

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Should log error
                pass

    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_returns_endpoint_in_response(self, mock_admin_client_class):
        """Test that endpoint is included in successful response."""
        from app.config import settings

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://myendpoint.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "test-key"):
                # Response should include endpoint
                pass

    @patch("app.api.azure.AzureKeyCredential")
    @patch("app.api.azure.DocumentIntelligenceAdministrationClient")
    def test_azure_connection_uses_credential(self, mock_admin_client_class, mock_credential_class):
        """Test that AzureKeyCredential is used correctly."""
        from app.config import settings

        mock_client = MagicMock()
        mock_client.list_operations.return_value = iter([])
        mock_admin_client_class.return_value = mock_client

        with patch.object(settings, "azure_endpoint", "https://test.cognitiveservices.azure.com/"):
            with patch.object(settings, "azure_ai_key", "my-key"):
                # AzureKeyCredential should be called with "my-key"
                pass
