import logging
import os

logger = logging.getLogger(__name__)


def update_env_file(settings_to_update: dict[str, str]) -> bool:
    """
    Updates the .env file with the given settings (best-effort).
    Creates or modifies existing keys.

    Args:
        settings_to_update: A dictionary mapping uppercase env var names to their new string values.

    Returns:
        True if the file was successfully updated, False otherwise.
    """
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if not os.path.exists(env_path):
            logger.warning(f".env file not found at {env_path}, skipping file write")
            return False

        logger.info(f"Updating settings in {env_path}")

        with open(env_path, "r") as f:
            env_lines = f.readlines()

        updated = set()
        new_env_lines = []
        for line in env_lines:
            stripped_line = line.rstrip()
            is_updated = False
            for key, value in settings_to_update.items():
                if stripped_line.startswith(f"{key}=") or stripped_line.startswith(f"# {key}="):
                    new_env_lines.append(f"{key}={value}")
                    updated.add(key)
                    is_updated = True
                    break
            if not is_updated:
                new_env_lines.append(stripped_line)

        for key, value in settings_to_update.items():
            if key not in updated:
                new_env_lines.append(f"{key}={value}")

        with open(env_path, "w") as f:
            f.write("\n".join(new_env_lines) + "\n")

        logger.info("Successfully updated settings in .env file")
        return True
    except Exception as env_err:
        logger.warning(f"Failed to write .env file (non-fatal): {env_err}")
        return False
