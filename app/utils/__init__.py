"""
Utility functions and helpers for the document processor application.
"""

# Import functions to make them available through the package
from app.utils.file_operations import hash_file
from app.utils.filename_utils import get_unique_filepath_with_counter, sanitize_filename
from app.utils.logging import log_task_progress

# Export all the functions that should be available when importing from app.utils
__all__ = ["hash_file", "log_task_progress", "get_unique_filepath_with_counter", "sanitize_filename"]
