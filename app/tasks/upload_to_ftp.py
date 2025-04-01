#!/usr/bin/env python3

import os
import ftplib
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery
import logging

logger = logging.getLogger(__name__)

@celery.task(base=BaseTaskWithRetry)
def upload_to_ftp(file_path: str):
    """Uploads a file to an FTP server in the configured folder."""

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename
    filename = os.path.basename(file_path)

    # Check if FTP settings are configured
    if not settings.ftp_host:
        error_msg = "FTP host is not configured"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        # Connect to FTP server
        ftp = ftplib.FTP()
        ftp.connect(
            host=settings.ftp_host,
            port=settings.ftp_port or 21
        )
        
        # Login with credentials
        ftp.login(
            user=settings.ftp_username, 
            passwd=settings.ftp_password
        )
        
        # Change to target directory if specified
        if settings.ftp_folder:
            try:
                # Try to navigate to the directory, create if it doesn't exist
                ftp_folder = settings.ftp_folder
                # Remove leading slash if present
                if ftp_folder.startswith('/'):
                    ftp_folder = ftp_folder[1:]
                
                # Try to change to the directory
                try:
                    ftp.cwd(ftp_folder)
                except ftplib.error_perm:
                    # Create directory structure if it doesn't exist
                    folders = ftp_folder.split('/')
                    current_dir = ''
                    for folder in folders:
                        if folder:
                            current_dir += f"/{folder}"
                            try:
                                ftp.cwd(current_dir)
                            except ftplib.error_perm:
                                ftp.mkd(current_dir)
                                ftp.cwd(current_dir)
            except ftplib.Error as e:
                error_msg = f"Failed to change/create directory on FTP server: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)
        
        # Upload the file
        with open(file_path, 'rb') as file_data:
            ftp.storbinary(f'STOR {filename}', file_data)
        
        # Close FTP connection
        ftp.quit()
        
        logger.info(f"Successfully uploaded {filename} to FTP server at {settings.ftp_host}")
        return {
            "status": "Completed", 
            "file": file_path, 
            "ftp_host": settings.ftp_host,
            "ftp_path": f"{settings.ftp_folder}/{filename}" if settings.ftp_folder else filename
        }
    
    except Exception as e:
        error_msg = f"Failed to upload {filename} to FTP server: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
