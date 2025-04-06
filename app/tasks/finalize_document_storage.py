#!/usr/bin/env python3

import os
import requests
import logging
import tempfile
import subprocess
from typing import Optional, List
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
# Import the shared Celery instance
from app.celery_app import celery

# 1) Import the aggregator task
from app.tasks.send_to_all import send_to_all_destinations

logger = logging.getLogger(__name__)


def convert_pdf_to_pdfa(input_file: str, output_file: str, pdfa_level: str = '2'):
    """
    Convert a PDF to PDF/A using Ghostscript.
    
    Args:
        input_file: Path to the input PDF
        output_file: Path to the output PDF/A
        pdfa_level: '1', '2', or '3' (default: '2')
    """
    if pdfa_level not in {'1', '2', '3'}:
        raise ValueError("PDF/A level must be '1', '2', or '3'")
    
    gs_command = [
        'gs',
        f'-dPDFA={pdfa_level}',
        '-dBATCH',
        '-dNOPAUSE',
        '-dNOOUTERSAVE',
        '-sProcessColorModel=DeviceRGB',
        '-sDEVICE=pdfwrite',
        '-sPDFACompatibilityPolicy=1',
        f'-sOutputFile={output_file}',
        input_file
    ]
    
    logger.info(f"Running Ghostscript PDF/A conversion: {' '.join(gs_command)}")
    
    subprocess.run(gs_command, check=True)
    
    logger.info(f"PDF/A-{pdfa_level} created at {output_file}")


@celery.task(name="convert_to_pdfa")
def convert_to_pdfa(file_path: str, pdfa_level: Optional[str] = None):
    """
    Convert a PDF file to PDF/A using Ghostscript.
    
    Args:
        file_path: Path to the PDF file to convert
        pdfa_level: PDF/A compliance level (1, 2, 3)
    
    Returns:
        Path to the created PDF/A file
    """
    logger.info(f"Starting PDF/A conversion for {file_path}")
    
    # Validate input file exists
    if not os.path.exists(file_path):
        logger.error(f"Input file not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Check if it's a PDF file
    if not file_path.lower().endswith('.pdf'):
        logger.error(f"File must be a PDF: {file_path}")
        raise ValueError(f"Only PDF files can be converted to PDF/A")
    
    # Use settings.pdf_pdfa_level if pdfa_level is not provided
    if pdfa_level is None:
        pdfa_level = getattr(settings, 'pdf_pdfa_level', '2')  # Default to 2 for better compatibility
    
    # Validate PDF/A level
    if pdfa_level not in ['1', '2', '3']:
        logger.warning(f"Invalid PDF/A level: {pdfa_level}, defaulting to 2")
        pdfa_level = '2'
    
    # Generate output filename
    output_dir = os.path.dirname(file_path)
    output_filename = f"{os.path.splitext(os.path.basename(file_path))[0]}_pdfa.pdf"
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        # Call the Ghostscript conversion function
        logger.info(f"Converting {file_path} to PDF/A-{pdfa_level}")
        convert_pdf_to_pdfa(file_path, output_path, pdfa_level)
        
        logger.info(f"Successfully converted {file_path} to PDF/A-{pdfa_level} at {output_path}")
        return output_path
        
    except Exception as e:
        logger.exception(f"Error during PDF/A conversion with Ghostscript: {e}")
        raise


@celery.task(base=BaseTaskWithRetry)
def finalize_document_storage(original_file: str, processed_file: str, metadata: dict):
    """
    Final storage step after embedding metadata.
    We will now call 'send_to_all_destinations' to push the final PDF to Dropbox/Nextcloud/Paperless.
    
    If PDF/A generation is enabled, we'll first convert the file to PDF/A format.
    """
    print(f"[INFO] Finalizing document storage for {processed_file}")

    # Check if we should generate PDF/A variant
    if settings.pdf_generate_pdfa:
        print(f"[INFO] Converting {processed_file} to PDF/A format")
        try:
            pdfa_file = convert_to_pdfa(processed_file)
            # If conversion was successful, use the PDF/A file instead
            processed_file = pdfa_file
            print(f"[INFO] Using PDF/A variant: {processed_file}")
        except Exception as e:
            logger.error(f"Failed to convert {processed_file} to PDF/A: {e}")

    # 2) Enqueue uploads to all destinations (Dropbox, Nextcloud, Paperless)
    send_to_all_destinations.delay(processed_file)

    return {
        "status": "Completed",
        "file": processed_file
    }
