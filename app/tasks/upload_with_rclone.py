#!/usr/bin/env python3

import os
import subprocess
import json
import tempfile
import logging
from pathlib import Path
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

logger = logging.getLogger(__name__)

@celery.task(base=BaseTaskWithRetry)
def upload_with_rclone(file_path: str, destination: str):
    """
    Uploads a file using rclone to the specified destination.
    
    Args:
        file_path: Path to the file to upload
        destination: Rclone destination in format "remote:path/to/folder"
                     e.g. "gdrive:Uploads" or "dropbox:Documents/Uploads"
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Extract filename
    filename = os.path.basename(file_path)
    
    # Check if rclone is installed and config exists
    rclone_config_path = os.path.join(settings.workdir, "rclone.conf")
    if not os.path.exists(rclone_config_path):
        error_msg = f"Rclone configuration not found at {rclone_config_path}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        # Split destination into remote and path
        if ":" not in destination:
            raise ValueError(f"Invalid destination format: {destination}. Expected format: remote:path")
        
        remote, remote_path = destination.split(":", 1)
        
        # Ensure the remote path exists (create folders if needed)
        mkdir_cmd = [
            "rclone", 
            "mkdir", 
            "--config", rclone_config_path,
            destination
        ]
        
        subprocess.run(mkdir_cmd, check=True, capture_output=True)
        
        # Construct the upload command
        upload_cmd = [
            "rclone", 
            "copy",
            "--config", rclone_config_path,
            file_path,
            destination,
            "--progress"
        ]
        
        # Execute the upload command
        result = subprocess.run(upload_cmd, check=True, capture_output=True, text=True)
        
        # Check if upload was successful
        if result.returncode == 0:
            # Try to get a public link if possible
            try:
                link_cmd = [
                    "rclone",
                    "link",
                    "--config", rclone_config_path,
                    f"{destination}/{filename}"
                ]
                link_result = subprocess.run(link_cmd, capture_output=True, text=True)
                public_url = link_result.stdout.strip() if link_result.returncode == 0 else None
            except Exception:
                public_url = None
            
            logger.info(f"Successfully uploaded {filename} to {destination}")
            return {
                "status": "Completed",
                "file": file_path,
                "destination": destination,
                "public_url": public_url
            }
        else:
            error_msg = f"Failed to upload {filename} to {destination}: {result.stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
    except subprocess.CalledProcessError as e:
        error_msg = f"Rclone error: {e.stderr.decode('utf-8') if hasattr(e.stderr, 'decode') else e.stderr}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    except Exception as e:
        error_msg = f"Error uploading {filename} to {destination}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


@celery.task(base=BaseTaskWithRetry)
def send_to_all_rclone_destinations(file_path: str):
    """
    Uploads a file to all configured rclone destinations.
    Destinations are loaded from the rclone configuration file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)
    
    # Path to rclone config
    rclone_config_path = os.path.join(settings.workdir, "rclone.conf")
    if not os.path.exists(rclone_config_path):
        error_msg = f"Rclone configuration not found at {rclone_config_path}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Get list of configured destinations from rclone
    try:
        remotes_cmd = ["rclone", "listremotes", "--config", rclone_config_path]
        result = subprocess.run(remotes_cmd, check=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Process the list of remotes
            remotes = [r.strip() for r in result.stdout.splitlines() if r.strip()]
            
            # Target directories for each remote (from settings)
            remote_paths = {}
            for remote in remotes:
                remote_name = remote.rstrip(':')
                path_setting_name = f"rclone_{remote_name}_path"
                if hasattr(settings, path_setting_name) and getattr(settings, path_setting_name):
                    remote_paths[remote] = getattr(settings, path_setting_name)
                else:
                    # Default to root of remote if not specified
                    remote_paths[remote] = ""
            
            # Queue upload tasks for each configured destination
            results = {}
            for remote, path in remote_paths.items():
                full_destination = f"{remote}{path}"
                if path and not path.endswith('/'):
                    full_destination += '/'
                
                logger.info(f"Queueing {file_path} for upload to {full_destination}")
                task = upload_with_rclone.delay(file_path, full_destination)
                results[f"rclone_{remote.rstrip(':')}_task_id"] = task.id
            
            return {
                "status": "Queued",
                "file_path": file_path,
                "tasks": results
            }
        else:
            error_msg = f"Failed to list rclone remotes: {result.stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = f"Error setting up rclone uploads for {filename}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
