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
        # First attempt FTPS (FTP with TLS)
        use_tls = getattr(settings, 'ftp_use_tls', True)  # Default to try TLS
        allow_plaintext = getattr(settings, 'ftp_allow_plaintext', True)  # Default to allow plaintext fallback
        
        if use_tls:
            try:
                logger.info(f"Attempting FTPS connection to {settings.ftp_host}")
                ftp = ftplib.FTP_TLS()
                ftp.connect(
                    host=settings.ftp_host,
                    port=settings.ftp_port or 21
                )
                
                # Login with credentials
                ftp.login(
                    user=settings.ftp_username, 
                    passwd=settings.ftp_password
                )
                
                # Enable data protection - encrypt the data channel
                ftp.prot_p()
                logger.info("Successfully established FTPS connection with TLS")
            except Exception as e:
                if not allow_plaintext:
                    error_msg = f"FTPS connection failed and plaintext FTP is forbidden: {str(e)}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                else:
                    logger.warning(f"FTPS connection failed, falling back to regular FTP: {str(e)}")
                    # Fall back to regular FTP
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
        else:
            # Check if plaintext is allowed when TLS is explicitly disabled
            if not allow_plaintext:
                error_msg = "Plaintext FTP is forbidden by configuration"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # Directly use regular FTP if TLS is explicitly disabled
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
            "ftp_path": f"{settings.ftp_folder}/{filename}" if settings.ftp_folder else filename,
            "used_tls": isinstance(ftp, ftplib.FTP_TLS)
        }
    
    except Exception as e:
        error_msg = f"Failed to upload {filename} to FTP server: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
