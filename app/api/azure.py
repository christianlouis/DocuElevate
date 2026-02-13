"""
Azure AI API endpoints
"""

import logging

import azure.core.exceptions
from azure.ai.documentintelligence import DocumentIntelligenceAdministrationClient

# Import the Azure modules including the administration client
from azure.core.credentials import AzureKeyCredential
from fastapi import APIRouter, Request

from app.auth import require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


def _check_azure_config() -> dict | None:
    """Return an error response dict if Azure config is incomplete, else None."""
    if settings.azure_endpoint and settings.azure_ai_key:
        return None
    missing = []
    if not settings.azure_endpoint:
        missing.append("endpoint")
    if not settings.azure_ai_key:
        missing.append("API key")
    return {
        "status": "error",
        "message": f"Azure Document Intelligence configuration is incomplete. Missing: {', '.join(missing)}",
    }


def _parse_operations(operations) -> list[dict]:
    """Extract operation info dicts from Azure operation objects."""
    operations_info = []
    for op in operations:
        if hasattr(op, "operation_id") and op.operation_id:
            operations_info.append(
                {
                    "id": op.operation_id,
                    "status": op.status if hasattr(op, "status") else "Unknown",
                    "created": str(op.created_on) if hasattr(op, "created_on") else "Unknown",
                    "kind": op.kind if hasattr(op, "kind") else "Unknown",
                }
            )
    return operations_info


@router.get("/azure/test")
@require_login
async def test_azure_connection(request: Request):
    """
    Test if the configured Azure Document Intelligence connection is valid.
    Uses the DocumentIntelligenceAdministrationClient for testing the connection.
    """
    try:
        logger.info("Testing Azure Document Intelligence connection")

        config_error = _check_azure_config()
        if config_error:
            logger.warning("Azure Document Intelligence configuration is incomplete")
            return config_error

        try:
            admin_client = DocumentIntelligenceAdministrationClient(
                endpoint=settings.azure_endpoint, credential=AzureKeyCredential(settings.azure_ai_key)
            )
            operations = list(admin_client.list_operations())
            logger.info("Azure Document Intelligence Admin connection successfully tested")

            try:
                operations_info = _parse_operations(operations)
                op_count = len(operations_info)
                return {
                    "status": "success",
                    "message": f"Azure Document Intelligence connection is valid. Found {op_count} operations.",
                    "endpoint": settings.azure_endpoint,
                    "operations_count": op_count,
                    "recent_operations": operations_info[:3] if operations_info else [],
                }
            except Exception as e:
                logger.warning(f"Connected to Azure but couldn't parse operations: {e}")
                return {
                    "status": "success",
                    "message": "Azure Document Intelligence connection is valid, "
                    "but couldn't retrieve operations details.",
                    "endpoint": settings.azure_endpoint,
                }

        except azure.core.exceptions.ClientAuthenticationError as e:
            logger.error(f"Azure authentication error: {e}")
            return {
                "status": "error",
                "message": "Authentication error: Invalid API key or credentials",
                "detail": str(e),
            }
        except azure.core.exceptions.ServiceRequestError as e:
            logger.error(f"Azure service request error: {e}")
            return {
                "status": "error",
                "message": "Service request error: Could not reach the Azure endpoint",
                "detail": str(e),
            }
        except ValueError as e:
            logger.error(f"Azure configuration value error: {e}")
            return {"status": "error", "message": f"Configuration error: {str(e)}", "detail": str(e)}
        except Exception as e:
            logger.error(f"Azure connection test failed with unexpected error: {e}")
            return {"status": "error", "message": "Connection test failed with unexpected error", "detail": str(e)}

    except Exception as e:
        logger.exception("Unexpected error testing Azure Document Intelligence connection")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}
