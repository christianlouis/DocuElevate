import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def get_unique_filename(original_path, check_exists_func=None):
    """
    Generates a unique filename by appending a timestamp or counter when a collision occurs.

    Args:
        original_path (str): The original file path
        check_exists_func (callable): Function that checks if file exists in target system.
                                     Takes a path string and returns True if exists, False otherwise.
                                     If None, will use local filesystem check.

    Returns:
        str: A unique filename that doesn't collide with existing files
    """
    if check_exists_func is None:
        check_exists_func = os.path.exists

    path = Path(original_path)
    directory = str(path.parent)
    filename = path.name
    name, ext = os.path.splitext(filename)

    # If file doesn't exist, return the original
    if not check_exists_func(original_path):
        return original_path

    # Try timestamp-based suffix first (more user-friendly)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_filename = f"{name}_{timestamp}{ext}"
    new_path = os.path.join(directory, new_filename)

    if not check_exists_func(new_path):
        logger.info(f"Renamed '{filename}' to '{new_filename}' to avoid collision")
        return new_path

    # If timestamp-based name also exists, try random UUID
    uuid_str = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for brevity
    new_filename = f"{name}_{uuid_str}{ext}"
    new_path = os.path.join(directory, new_filename)

    if not check_exists_func(new_path):
        logger.info(f"Renamed '{filename}' to '{new_filename}' using UUID to avoid collision")
        return new_path

    # If that still exists (very unlikely), use incremental numbering
    counter = 1
    while counter < 1000:  # Limit to avoid infinite loop
        new_filename = f"{name}_{counter}{ext}"
        new_path = os.path.join(directory, new_filename)
        if not check_exists_func(new_path):
            logger.info(f"Renamed '{filename}' to '{new_filename}' using counter to avoid collision")
            return new_path
        counter += 1

    # If we got here, something is weird - just use a full UUID
    new_filename = f"{name}_{str(uuid.uuid4())}{ext}"
    new_path = os.path.join(directory, new_filename)
    logger.warning(f"Had to use full UUID to rename '{filename}' to '{new_filename}'")

    return new_path


def get_unique_filepath_with_counter(directory, base_filename, extension=".pdf"):
    """
    Returns a unique filepath in the specified directory using a numeric counter suffix.
    If 'base_filename.pdf' exists, it will append '-0001', '-0002', etc.

    This function implements robust collision handling with zero-padded numeric suffixes
    as required for document storage organization.

    Args:
        directory (str): Directory path where the file will be stored
        base_filename (str): Base name for the file (without extension)
        extension (str): File extension including the dot (default: ".pdf")

    Returns:
        str: Full path to a unique filename

    Examples:
        >>> get_unique_filepath_with_counter("/workdir/original", "2024-01-01_Invoice")
        "/workdir/original/2024-01-01_Invoice.pdf"  # If doesn't exist

        >>> get_unique_filepath_with_counter("/workdir/original", "2024-01-01_Invoice")
        "/workdir/original/2024-01-01_Invoice-0001.pdf"  # If original exists
    """
    # Try the base filename first
    candidate = os.path.join(directory, base_filename + extension)
    if not os.path.exists(candidate):
        return candidate

    # If base exists, try with counter suffix
    counter = 1
    while True:
        # Use zero-padded 4-digit counter: -0001, -0002, etc.
        suffix = f"-{counter:04d}"
        candidate = os.path.join(directory, f"{base_filename}{suffix}{extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

        # Sanity check to prevent infinite loops (very unlikely to reach)
        if counter > 9999:
            # Fall back to timestamp + UUID if somehow we have 10000 collisions
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            uuid_str = str(uuid.uuid4())[:8]
            candidate = os.path.join(directory, f"{base_filename}-{timestamp}-{uuid_str}{extension}")
            logger.warning(
                f"Exceeded 9999 file collisions for {base_filename}, "
                f"using timestamp+UUID: {os.path.basename(candidate)}"
            )
            return candidate


def sanitize_filename(filename):
    r"""
    Sanitize a filename to ensure it's valid across different file systems
    and prevent path traversal attacks.

    Args:
        filename (str): The filename to sanitize

    Returns:
        str: A sanitized filename

    Security:
        - Removes path separators (/ and \)
        - Prevents path traversal patterns (..)
        - Replaces problematic characters with underscores
        - Ensures compatibility across Windows, Linux, and macOS
    """
    # First, replace all path separators (both Unix and Windows style) with underscores
    sanitized = filename.replace("/", "_").replace("\\", "_")

    # Replace characters that are problematic in various filesystems
    # Keep only alphanumeric, dash, underscore, period, and space
    sanitized = re.sub(r"[^\w\-\. ]", "_", sanitized)

    # Remove or replace path traversal patterns
    # Replace specifically '..' to prevent path traversal while preserving single dots
    sanitized = sanitized.replace("..", "_")

    # Replace multiple spaces/underscores with single ones
    sanitized = re.sub(r"__+", "_", sanitized)
    sanitized = re.sub(r"  +", " ", sanitized)

    # Trim leading/trailing spaces, periods, and underscores which cause issues in Windows
    sanitized = sanitized.strip(". _")

    # Ensure the filename isn't empty after sanitization
    if not sanitized or sanitized == ".":
        sanitized = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    return sanitized


def extract_remote_path(file_path, base_dir, remote_base=""):
    """
    Extract a remote path for a file by preserving its directory structure
    relative to the base directory, but with a new remote base path.

    Modified to skip 'processed' directory in the remote path.
    """
    # Normalize paths for consistent handling across platforms
    file_path = os.path.normpath(file_path)
    base_dir = os.path.normpath(base_dir)

    # Get relative path from base directory
    if file_path.startswith(base_dir):
        rel_path = os.path.relpath(file_path, base_dir)
    else:
        # If not a subdirectory of base_dir, just use the filename
        rel_path = os.path.basename(file_path)

    # Skip 'processed' directory if it's in the path
    path_parts = rel_path.split(os.sep)
    if "processed" in path_parts:
        # Remove 'processed' from the path
        path_parts.remove("processed")
        rel_path = os.path.join(*path_parts)

    # Combine with remote base path
    if remote_base:
        if remote_base.startswith("/"):
            # Handle absolute path for services like Dropbox
            remote_path = os.path.join(remote_base[1:], rel_path)
        else:
            remote_path = os.path.join(remote_base, rel_path)
    else:
        remote_path = rel_path

    # Convert to forward slashes for compatibility with most cloud services
    remote_path = remote_path.replace(os.sep, "/")

    return remote_path
