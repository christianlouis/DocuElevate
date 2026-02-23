"""
Worker settings synchronisation helper.

When an admin saves a configuration change through the UI, any running Celery
workers still hold the *old* values in their in-process ``settings`` singleton.
This module provides two complementary mechanisms to propagate the change:

1. **Publish** (API side): :func:`notify_settings_updated` writes a monotonically
   increasing timestamp to a Redis key.  This is called immediately after every
   successful ``save_setting_to_db`` / ``delete_setting_from_db`` operation.

2. **Subscribe** (worker side): :func:`register_settings_reload_signal` installs
   a Celery ``task_prerun`` signal handler.  Before each task begins the handler
   reads the Redis version key; if it has changed since the last reload it calls
   :func:`~app.utils.config_loader.reload_settings_from_db` so the worker picks
   up the new values *before* executing the task body.

The Redis key used is ``docuelevate:settings_version``.  Workers cache the last
seen version in a module-level variable to avoid redundant DB round-trips when
nothing has changed.
"""

import logging
import time
from typing import Any

import redis
from celery.signals import task_prerun

logger = logging.getLogger(__name__)

#: Redis key that stores the current settings "version" (epoch timestamp string).
SETTINGS_VERSION_KEY = "docuelevate:settings_version"

#: Module-level cache: the settings version seen by *this* process on its last reload.
_last_seen_version: str = ""


def notify_settings_updated() -> None:
    """
    Publish a settings-updated signal by updating the Redis version key, and
    immediately reload the in-process ``settings`` singleton so the API
    process serves fresh values without a restart.

    Call this after every successful settings write so that all worker
    processes know they need to reload their in-memory configuration.

    Errors are caught and logged rather than raised so that a Redis
    connectivity issue does not prevent the primary save from succeeding.
    """
    try:
        from app.config import settings

        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        version = str(time.time())
        r.set(SETTINGS_VERSION_KEY, version)
        logger.debug(f"Settings version bumped to {version}")
    except Exception as exc:
        logger.warning(f"Could not publish settings update to Redis: {exc}")

    # Reload the in-process settings singleton immediately so the API node
    # returns updated values (e.g. oauth_provider_name on the login page)
    # without needing a restart.  Workers use the task_prerun signal handler
    # instead, so this only affects the API/web process.
    try:
        from app.config import settings
        from app.utils.config_loader import reload_settings_from_db

        reload_settings_from_db(settings)
        logger.debug("In-process settings reloaded after settings update")
    except Exception as exc:
        logger.warning(f"Could not reload in-process settings: {exc}")


def register_settings_reload_signal() -> None:
    """
    Install a Celery ``task_prerun`` signal handler for worker processes.

    This should be called once during Celery worker initialisation (e.g. from
    ``celery_worker.py``).  After registration, every task will check the
    settings version key in Redis before it starts and reload configuration
    from the database if a newer version is detected.
    """

    @task_prerun.connect(weak=False)
    def _reload_if_stale(sender: Any, **kwargs: Any) -> None:
        """Reload settings from DB if the Redis version key has changed."""
        global _last_seen_version
        try:
            from app.config import settings
            from app.utils.config_loader import reload_settings_from_db

            r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
            current_version = (r.get(SETTINGS_VERSION_KEY) or b"").decode()
            if current_version and current_version != _last_seen_version:
                reload_settings_from_db(settings)
                _last_seen_version = current_version
                logger.info(f"Worker settings reloaded (version={current_version})")
        except Exception as exc:
            logger.debug(f"Settings version check skipped: {exc}")

    logger.info("Settings reload signal handler registered on task_prerun")
