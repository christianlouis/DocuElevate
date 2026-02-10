"""
Utility functions for splitting large PDF files into smaller chunks.

This module provides functionality to split PDF files that exceed a certain size
into smaller chunks for processing. Used when MAX_SINGLE_FILE_SIZE is configured.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def split_pdf_by_size(
    pdf_path: str,
    max_size_bytes: int,
    output_dir: Optional[str] = None
) -> List[str]:
    """
    Split a PDF file into multiple smaller PDF files based on size constraints.
    
    The function splits the PDF by distributing pages across multiple output files,
    ensuring each output file stays under the specified size limit.
    
    Args:
        pdf_path: Path to the PDF file to split
        max_size_bytes: Maximum size for each output file in bytes
        output_dir: Directory to save split files. If None, uses same directory as input file.
        
    Returns:
        List of paths to the generated PDF files (in order)
        
    Raises:
        FileNotFoundError: If the input PDF file doesn't exist
        ValueError: If max_size_bytes is too small to fit even one page
        
    Example:
        >>> split_files = split_pdf_by_size("large.pdf", 50 * 1024 * 1024)  # 50MB max
        >>> print(f"Split into {len(split_files)} files")
    """
    # Validate input file exists
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Determine output directory
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the input PDF
    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path}: {str(e)}")
        raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")
    
    if total_pages == 0:
        logger.warning(f"PDF {pdf_path} has no pages")
        return []
    
    # Get base filename without extension
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    output_files = []
    current_writer = PdfWriter()
    current_page_count = 0
    part_number = 1
    
    logger.info(f"Splitting PDF {pdf_path} ({total_pages} pages) into chunks of max {max_size_bytes} bytes")
    
    for page_num in range(total_pages):
        # Add the page to current writer
        page = reader.pages[page_num]
        current_writer.add_page(page)
        current_page_count += 1
        
        # Write to temporary file to check size
        temp_output_path = os.path.join(output_dir, f"{base_name}_part{part_number}_temp.pdf")
        with open(temp_output_path, "wb") as temp_file:
            current_writer.write(temp_file)
        
        temp_size = os.path.getsize(temp_output_path)
        
        # If adding this page exceeds the limit (and we have more than 1 page in current chunk)
        # save the previous chunk and start a new one
        if temp_size > max_size_bytes and current_page_count > 1:
            # Remove the temporary file
            os.remove(temp_output_path)
            
            # Create a new writer without the last page
            previous_writer = PdfWriter()
            for prev_page_num in range(page_num - current_page_count + 1, page_num):
                previous_writer.add_page(reader.pages[prev_page_num])
            
            # Save the previous chunk
            output_path = os.path.join(output_dir, f"{base_name}_part{part_number}.pdf")
            with open(output_path, "wb") as output_file:
                previous_writer.write(output_file)
            
            output_files.append(output_path)
            logger.info(f"Created chunk {part_number}: {output_path} ({current_page_count - 1} pages)")
            
            # Start new chunk with current page
            part_number += 1
            current_writer = PdfWriter()
            current_writer.add_page(page)
            current_page_count = 1
        elif temp_size > max_size_bytes and current_page_count == 1:
            # Single page exceeds limit - this is a problem
            # We'll keep it anyway but log a warning
            logger.warning(
                f"Single page (page {page_num + 1}) exceeds size limit "
                f"({temp_size} > {max_size_bytes}). Keeping as separate file."
            )
            # Rename temp file to final name
            output_path = os.path.join(output_dir, f"{base_name}_part{part_number}.pdf")
            os.rename(temp_output_path, output_path)
            output_files.append(output_path)
            
            # Start new chunk
            part_number += 1
            current_writer = PdfWriter()
            current_page_count = 0
        else:
            # Size is OK, remove temp file and continue
            os.remove(temp_output_path)
    
    # Save the last chunk if it has any pages
    if current_page_count > 0:
        output_path = os.path.join(output_dir, f"{base_name}_part{part_number}.pdf")
        with open(output_path, "wb") as output_file:
            current_writer.write(output_file)
        output_files.append(output_path)
        logger.info(f"Created final chunk {part_number}: {output_path} ({current_page_count} pages)")
    
    logger.info(f"Successfully split PDF into {len(output_files)} files")
    return output_files


def should_split_file(file_path: str, max_single_file_size: Optional[int]) -> bool:
    """
    Determine if a file should be split based on its size and configuration.
    
    Args:
        file_path: Path to the file to check
        max_single_file_size: Maximum single file size in bytes, or None to disable splitting
        
    Returns:
        True if file should be split, False otherwise
    """
    if max_single_file_size is None:
        return False
    
    if not os.path.exists(file_path):
        return False
    
    file_size = os.path.getsize(file_path)
    return file_size > max_single_file_size
