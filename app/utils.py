# app/utils.py
# This file is deprecated. Functions have been moved to the utils package.
# To avoid breaking existing imports, we'll import and re-export the functions
from app.utils.file_operations import hash_file  # noqa: F401
from app.utils.logging import log_task_progress  # noqa: F401

# These functions are now available directly from the app.utils package
