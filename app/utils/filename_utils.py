import os
import re
import uuid
import logging
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

def sanitize_filename(filename):
    """
    Sanitize a filename to ensure it's valid across different file systems.
    
    Args:
        filename (str): The filename to sanitize
        
    Returns:
        str: A sanitized filename
    """
    # Replace characters that are problematic in various filesystems
    # Keep only alphanumeric, dash, underscore, period, and space
    sanitized = re.sub(r'[^\w\-\. ]', '_', filename)
    
    # Replace multiple spaces/underscores with single ones
    sanitized = re.sub(r'__+', '_', sanitized)
    sanitized = re.sub(r'  +', ' ', sanitized)
    
    # Trim leading/trailing spaces and periods which cause issues in Windows
    sanitized = sanitized.strip('. ')
    
    # Ensure the filename isn't empty after sanitization
    if not sanitized or sanitized == '.':
        sanitized = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return sanitized

def extract_remote_path(local_path, base_dir, remote_base=None):
    """
    Extracts the appropriate remote path based on a local path structure.
    
    Args:
        local_path (str): The local file path
        base_dir (str): The local base directory to remove from path
        remote_base (str, optional): Remote base directory to prepend
        
    Returns:
        str: The calculated remote path
    """
    # Convert both paths to use forward slashes for consistency
    local_path = local_path.replace('\\', '/')
    base_dir = base_dir.replace('\\', '/')
    
    # Make sure base_dir ends with a slash
    if not base_dir.endswith('/'):
        base_dir += '/'
    
    # Remove the base directory from the local path
    if local_path.startswith(base_dir):
        relative_path = local_path[len(base_dir):]
    else:
        # If local_path is not within base_dir, just use the filename
        relative_path = os.path.basename(local_path)
    
    # Prepend the remote base if provided
    if remote_base:
        # Ensure remote_base ends with slash
        if not remote_base.endswith('/'):
            remote_base += '/'
        return remote_base + relative_path
    
    return relative_path
