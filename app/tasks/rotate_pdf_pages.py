import os
import logging
import PyPDF2
import math
import json

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery

logger = logging.getLogger(__name__)

def determine_rotation_angle(detected_angle):
    """
    Determine the optimal rotation angle based on detected angle.
    
    Args:
        detected_angle: The angle detected by Azure Document Intelligence
        
    Returns:
        int: The angle to rotate the page in PyPDF2 (must be multiple of 90 degrees)
    """
    # Normalize angle to be between 0 and 360
    normalized_angle = detected_angle % 360
    if normalized_angle < 0:
        normalized_angle += 360
    
    # If angle is very small (< 1 degree), don't rotate
    if abs(normalized_angle) < 1 or abs(normalized_angle - 360) < 1:
        return 0
    
    # For angles close to 90, 180, or 270 degrees (±5°), round to nearest 90° increment
    for target in [90, 180, 270]:
        if abs(normalized_angle - target) < 5:
            # PyPDF2 uses clockwise rotation, so we need to use the complementary angle
            rotation_value = (360 - target) % 360
            logger.info(f"Detected angle {detected_angle}° is close to {target}°, will rotate by {rotation_value}°")
            return rotation_value
    
    # For other significant angles, round to nearest 90° increment
    # (PyPDF2 only supports rotations in 90-degree increments)
    closest_90_multiple = round(normalized_angle / 90) * 90
    # Convert to PyPDF2 rotation value (clockwise)
    rotation_value = (360 - closest_90_multiple) % 360
    logger.info(f"Detected angle {detected_angle}° rounded to {closest_90_multiple}°, will rotate by {rotation_value}°")
    return rotation_value

@celery.task(base=BaseTaskWithRetry)
def rotate_pdf_pages(filename: str, extracted_text: str, rotation_data=None):
    """
    Rotates pages in a PDF document based on detected rotation angles.
    
    Args:
        filename: The name of the file to rotate
        extracted_text: The extracted text from the document
        rotation_data: Optional rotation data dictionary {page_index: angle}
    """
    try:
        pdf_path = os.path.join(settings.workdir, "tmp", filename)
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Skip rotation if no rotation data provided
        if not rotation_data:
            logger.info(f"No rotation data provided for {filename}, proceeding with metadata extraction")
            extract_metadata_with_gpt.delay(filename, extracted_text)
            return {"file": filename, "status": "no_rotation_needed"}

        # Standardize rotation_data keys to integers
        normalized_rotation_data = {}
        for key, value in rotation_data.items():
            try:
                normalized_rotation_data[int(key)] = float(value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid rotation data key-value: {key}:{value}")

        if not any(abs(angle) > 0 for angle in normalized_rotation_data.values()):
            logger.info(f"No significant rotations detected in {filename}, proceeding with metadata extraction")
            extract_metadata_with_gpt.delay(filename, extracted_text)
            return {"file": filename, "status": "no_rotation_needed"}
        
        logger.info(f"Rotating {len(normalized_rotation_data)} pages in {filename}")
        applied_rotations = {}
        
        # Load the PDF
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            pdf_writer = PyPDF2.PdfWriter()
            
            # Process each page
            for page_idx in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_idx]
                
                # Apply rotation if this page has rotation data
                if page_idx in normalized_rotation_data and abs(normalized_rotation_data[page_idx]) > 0:
                    detected_angle = normalized_rotation_data[page_idx]
                    rotation_angle = determine_rotation_angle(detected_angle)
                    
                    if rotation_angle > 0:
                        # PyPDF2 uses clockwise rotation in 90-degree increments
                        page.rotate(rotation_angle)
                        logger.info(f"Page {page_idx+1} rotated by {rotation_angle}° (from detected {detected_angle}°)")
                        applied_rotations[str(page_idx)] = rotation_angle
                    else:
                        logger.info(f"Page {page_idx+1} had detected angle {detected_angle}° but determined it doesn't need rotation")
                
                pdf_writer.add_page(page)
            
            # Save the rotated PDF
            with open(pdf_path, 'wb') as output_file:
                pdf_writer.write(output_file)
        
        if applied_rotations:
            logger.info(f"Successfully rotated PDF: {filename} with rotations: {json.dumps(applied_rotations)}")
        else:
            logger.info(f"Detected rotations in {filename} but no rotations were actually applied (angles too small or not multiples of 90°)")
        
        # Continue with metadata extraction
        extract_metadata_with_gpt.delay(filename, extracted_text)
        
        return {
            "file": filename, 
            "status": "rotated" if applied_rotations else "no_rotation_needed",
            "detected_rotations": rotation_data,
            "applied_rotations": applied_rotations
        }
        
    except Exception as e:
        logger.error(f"Error rotating PDF {filename}: {e}")
        # Continue with metadata extraction despite rotation failure
        extract_metadata_with_gpt.delay(filename, extracted_text)
        return {"file": filename, "status": "rotation_failed", "error": str(e)}
