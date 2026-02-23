import asyncio
import inspect
import json
import logging
import os
import time

from app.api.azure import test_azure_connection
from app.api.dropbox import test_dropbox_token
from app.api.google_drive import test_google_drive_token
from app.api.onedrive import test_onedrive_token

# Import the test functions from API routes
from app.api.openai import test_ai_provider_connection, test_openai_connection
from app.celery_app import celery
from app.config import settings

# Import config validation utilities
from app.utils.config_validator import get_provider_status, validate_storage_configs
from app.utils.notification import notify_credential_failure


# Create an enhanced mock Request object for API functions that expect it
class MockRequest:
    """Mock request object with session and other attributes needed for API functions"""

    def __init__(self):
        self.session = {"user": {"id": "credential_checker", "name": "System Credential Checker"}}
        self.app = None
        self.headers = {}
        self.query_params = {}
        self.path_params = {}

    async def json(self):
        return {}

    async def form(self):
        return {}


logger = logging.getLogger(__name__)

# Path to store failure counts
FAILURE_STATE_FILE = os.path.join(settings.workdir, "credential_failures.json")


def get_failure_state():
    """Read the failure state from file"""
    try:
        if os.path.exists(FAILURE_STATE_FILE):
            with open(FAILURE_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading failure state file: {e}")

    # Default empty state
    return {}


def save_failure_state(state):
    """Save failure state to file"""
    try:
        with open(FAILURE_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Error saving failure state file: {e}")


# Helper function to get the inner function without the decorator
def unwrap_decorated_function(func):
    """Get the original function from a decorated function"""
    if hasattr(func, "__wrapped__"):
        return unwrap_decorated_function(func.__wrapped__)
    return func


# Create synchronous versions of the test functions that bypass authentication
def sync_test_ai_provider_connection():
    """Synchronous wrapper for the AI provider test function that bypasses auth."""
    inner_func = unwrap_decorated_function(test_ai_provider_connection)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


def sync_test_openai_connection():
    """Synchronous wrapper for the OpenAI test function that bypasses auth."""
    # Get the original function without the @require_login decorator
    inner_func = unwrap_decorated_function(test_openai_connection)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


def sync_test_azure_connection():
    """Synchronous wrapper for the Azure test function that bypasses auth"""
    inner_func = unwrap_decorated_function(test_azure_connection)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


def sync_test_dropbox_token():
    """Synchronous wrapper for the Dropbox test function that bypasses auth"""
    inner_func = unwrap_decorated_function(test_dropbox_token)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


def sync_test_google_drive_token():
    """Synchronous wrapper for the Google Drive test function that bypasses auth"""
    inner_func = unwrap_decorated_function(test_google_drive_token)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


def sync_test_onedrive_token():
    """Synchronous wrapper for the OneDrive test function that bypasses auth"""
    inner_func = unwrap_decorated_function(test_onedrive_token)
    request = MockRequest()
    if inspect.iscoroutinefunction(inner_func):
        return asyncio.run(inner_func(request))
    return inner_func(request)


@celery.task
def check_credentials():
    """Check all configured credentials and notify if any are invalid"""
    logger.info("Starting credential check task")

    # Load current failure state
    failure_state = get_failure_state()

    # Track failures
    failures = []

    # Get provider configurations from config_validator
    provider_status = get_provider_status()
    storage_configs = validate_storage_configs()

    # Define services with their test functions and configuration status
    services = [
        {
            "name": "AI Provider",
            "check_func": sync_test_ai_provider_connection,
            "configured": provider_status.get("AI Provider", {}).get("configured", False),
            "config_issues": [],
        },
        {
            "name": "Azure Document Intelligence",
            "check_func": sync_test_azure_connection,
            "configured": provider_status.get("Azure AI", {}).get("configured", False),
            "config_issues": [],  # Azure isn't in storage_configs
        },
        {
            "name": "Dropbox",
            "check_func": sync_test_dropbox_token,
            "configured": provider_status.get("Dropbox", {}).get("configured", False),
            "config_issues": storage_configs.get("dropbox", []),
        },
        {
            "name": "Google Drive",
            "check_func": sync_test_google_drive_token,
            "configured": provider_status.get("Google Drive", {}).get("configured", False),
            "config_issues": storage_configs.get("google_drive", []),
        },
        {
            "name": "OneDrive",
            "check_func": sync_test_onedrive_token,
            "configured": provider_status.get("OneDrive", {}).get("configured", False),
            "config_issues": storage_configs.get("onedrive", []),
        },
    ]

    # Check each service
    results = {}
    current_time = int(time.time())

    for service in services:
        service_name = service["name"]
        logger.info(f"Checking credentials for {service_name}")

        # Skip services that aren't configured
        if not service["configured"]:
            config_issues = service["config_issues"]
            issue_msg = "Not properly configured" + (f": {', '.join(config_issues)}" if config_issues else "")
            logger.info(f"Skipping {service_name}: {issue_msg}")

            results[service_name] = {"status": "unconfigured", "message": issue_msg}
            continue

        try:
            # Call the synchronized test function and get the result
            result = service["check_func"]()

            # All test functions return a dict with "status" field
            is_valid = result.get("status") == "success"
            error_message = result.get("message", "Unknown error")

            # Store the result
            results[service_name] = {"status": "valid" if is_valid else "invalid", "message": error_message}

            if not is_valid:
                failures.append(service_name)

                # Get current failure count for this service
                service_state = failure_state.get(service_name, {"count": 0, "last_notified": 0})
                service_state["count"] = service_state.get("count", 0) + 1

                # Only notify if we haven't reached the notification threshold (3 failures)
                # or if this is the first failure after a recovery
                if service_state["count"] <= 3 or service_state.get("recovered", False):
                    notify_credential_failure(service_name, error_message)
                    service_state["last_notified"] = current_time
                    service_state["recovered"] = False
                    logger.warning(
                        f"{service_name} credentials check failed ({service_state['count']} times): {error_message}"
                    )
                else:
                    # We're in cooldown mode
                    logger.warning(
                        f"{service_name} credentials check failed ({service_state['count']} times): "
                        f"{error_message} - notification suppressed"
                    )

                # Update failure state
                failure_state[service_name] = service_state
            else:
                logger.info(f"{service_name} credentials are valid")

                # Check if this was previously failing and now recovered
                if service_name in failure_state and failure_state[service_name].get("count", 0) > 0:
                    logger.info(f"{service_name} has recovered after {failure_state[service_name]['count']} failures")

                    # Mark it as recovered and reset count
                    failure_state[service_name] = {"count": 0, "recovered": True, "last_notified": 0}
                elif service_name in failure_state:
                    # Just make sure recovered flag is cleared if it was there
                    failure_state[service_name]["recovered"] = True

        except Exception as e:
            logger.error(f"Error checking {service_name} credentials: {e}", exc_info=True)
            failures.append(service_name)
            error_message = f"Exception during credential check: {str(e)}"

            # Get current failure count for this service
            service_state = failure_state.get(service_name, {"count": 0, "last_notified": 0})
            service_state["count"] = service_state.get("count", 0) + 1

            # Only notify if we haven't reached the notification threshold or if we just recovered
            if service_state["count"] <= 3 or service_state.get("recovered", False):
                notify_credential_failure(service_name, error_message)
                service_state["last_notified"] = current_time
                service_state["recovered"] = False

            # Update failure state
            failure_state[service_name] = service_state

            # Store the error result
            results[service_name] = {"status": "error", "message": error_message}

    # Save updated failure state
    save_failure_state(failure_state)

    # Count only services that were actually checked (configured services)
    configured_services = [s for s in services if s["configured"]]
    num_configured = len(configured_services)

    # Summarize results
    logger.info(
        f"Credential check completed. Configured services: {num_configured}, "
        f"Valid: {num_configured - len(failures)}, Invalid: {len(failures)}"
    )

    return {
        "checked": num_configured,
        "unconfigured": len(services) - num_configured,
        "failures": len(failures),
        "results": results,
        "failure_state": failure_state,
    }
