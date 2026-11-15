import asyncio
import inspect
import json
import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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


def _redact_message(message):
    """Keep provider diagnostics useful without persisting likely secrets."""
    text = str(message or "Unknown error")
    return re.sub(
        r"(?i)(api[_ -]?key|token|secret|password)([\s:=\"']+)[^,\s}\"']+",
        r"\1\2[REDACTED]",
        text,
    )


def _record_credential_result(service_name, success, legacy_state):
    """Atomically update shared state and decide whether one notification is due.

    The legacy JSON is read only as a one-time seed for an empty database row. It
    is never written again, so a full or read-only work volume cannot corrupt the
    control-plane state.
    """
    from app.database import SessionLocal
    from app.models import CredentialCheckState

    for attempt in range(2):
        db = None
        try:
            db = SessionLocal()
            state = (
                db.query(CredentialCheckState)
                .with_for_update()
                .filter(CredentialCheckState.service_name == service_name)
                .one_or_none()
            )
            if state is None:
                previous = legacy_state.get(service_name, {})
                try:
                    previous_count = int(previous.get("count", 0) or 0)
                except (TypeError, ValueError):
                    previous_count = 0
                state = CredentialCheckState(
                    service_name=service_name,
                    failure_count=previous_count,
                    recovered=bool(previous.get("recovered", False)),
                )
                db.add(state)
                db.flush()

            should_notify = False
            if success:
                if state.failure_count > 0:
                    state.failure_count = 0
                    state.recovered = True
            else:
                state.failure_count += 1
                should_notify = state.failure_count <= 3 or state.recovered
                state.recovered = False
                if should_notify:
                    state.last_notified_at = datetime.now(timezone.utc)

            snapshot = {
                "count": state.failure_count,
                "recovered": state.recovered,
                "last_notified": (
                    int(state.last_notified_at.timestamp()) if state.last_notified_at else 0
                ),
            }
            db.commit()
            return snapshot, should_notify
        except IntegrityError:
            db.rollback()
            if attempt == 0:
                continue
            logger.error("Credential state insert raced for %s; state update skipped", service_name)
            return None, False
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Shared credential state unavailable for %s", service_name)
            return None, False
        finally:
            if db is not None:
                db.close()
    return None, False


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

    # Read legacy state only to seed a newly-created database row.
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
            "configured": provider_status.get("Dropbox", {}).get("configured", False)
            and provider_status.get("Dropbox", {}).get("enabled", True),
            "config_issues": storage_configs.get("dropbox", []),
        },
        {
            "name": "Google Drive",
            "check_func": sync_test_google_drive_token,
            "configured": provider_status.get("Google Drive", {}).get("configured", False)
            and provider_status.get("Google Drive", {}).get("enabled", True),
            "config_issues": storage_configs.get("google_drive", []),
        },
        {
            "name": "OneDrive",
            "check_func": sync_test_onedrive_token,
            "configured": provider_status.get("OneDrive", {}).get("configured", False)
            and provider_status.get("OneDrive", {}).get("enabled", True),
            "config_issues": storage_configs.get("onedrive", []),
        },
    ]

    # Check each service
    results = {}
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
            error_message = _redact_message(result.get("message", "Unknown error"))

            # Store the result
            results[service_name] = {"status": "valid" if is_valid else "invalid", "message": error_message}

            if not is_valid:
                failures.append(service_name)

                service_state, should_notify = _record_credential_result(service_name, False, failure_state)
                if service_state is None:
                    # Shared state is unavailable: keep this invocation safe, but do
                    # not fall back to the legacy file as a coordination mechanism.
                    service_state = failure_state.get(service_name, {"count": 0, "last_notified": 0}).copy()
                    service_state["count"] = service_state.get("count", 0) + 1
                    should_notify = False
                failure_state[service_name] = service_state

                if should_notify:
                    notify_credential_failure(service_name, error_message)
                    logger.warning(
                        f"{service_name} credentials check failed ({service_state['count']} times): {error_message}"
                    )
                else:
                    # We're in cooldown mode
                    logger.warning(
                        f"{service_name} credentials check failed ({service_state['count']} times): "
                        f"{error_message} - notification suppressed"
                    )

            else:
                logger.info(f"{service_name} credentials are valid")
                previous_count = failure_state.get(service_name, {}).get("count", 0)
                service_state, _ = _record_credential_result(service_name, True, failure_state)
                if service_state is not None:
                    failure_state[service_name] = service_state
                if previous_count:
                    logger.info(f"{service_name} has recovered after {previous_count} failures")

        except Exception as e:
            logger.error(f"Error checking {service_name} credentials: {e}", exc_info=True)
            failures.append(service_name)
            error_message = f"Exception during credential check: {_redact_message(e)}"

            service_state, should_notify = _record_credential_result(service_name, False, failure_state)
            if service_state is None:
                service_state = failure_state.get(service_name, {"count": 0, "last_notified": 0}).copy()
                service_state["count"] = service_state.get("count", 0) + 1
                should_notify = False
            failure_state[service_name] = service_state

            if should_notify:
                notify_credential_failure(service_name, error_message)

            # Store the error result
            results[service_name] = {"status": "error", "message": error_message}

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
