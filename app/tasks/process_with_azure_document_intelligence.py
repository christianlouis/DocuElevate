import logging
import os

import azure.core.exceptions
import PyPDF2
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeOutputOption, AnalyzeResult
from azure.core.credentials import AzureKeyCredential

from app.celery_app import celery
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.rotate_pdf_pages import rotate_pdf_pages

logger = logging.getLogger(__name__)

# Initialize Azure Document Intelligence client with error handling
try:
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint=settings.azure_endpoint, credential=AzureKeyCredential(settings.azure_ai_key)
    )
    logger.info("Azure Document Intelligence client initialized successfully")
except (ValueError, azure.core.exceptions.ClientAuthenticationError) as e:
    logger.error(f"Failed to initialize Azure Document Intelligence client: {e}")
    document_intelligence_client = None
except Exception as e:
    logger.error(f"Unexpected error initializing Azure Document Intelligence client: {e}")
    document_intelligence_client = None

# Azure Document Intelligence service limits for Standard S0 tier
AZURE_DOC_INTELLIGENCE_LIMITS = {
    "max_file_size_bytes": 500 * 1024 * 1024,  # 500 MB
    "max_pages": 2000,
}


def get_pdf_page_count(file_path):
    """Get the number of pages in a PDF file."""
    try:
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            return len(pdf_reader.pages)
    except Exception as e:
        logger.error(f"Error getting PDF page count: {e}")
        return None


def check_page_rotation(result, filename):
    """
    Checks if pages in the document are rotated and logs the rotation information.

    Args:
        result: The AnalyzeResult from Azure Document Intelligence API
        filename: The name of the file being processed

    Returns:
        dict: Dictionary mapping page indices (integers) to rotation angles
    """
    logger.error(f"Checking rotation for document: {filename}")
    rotation_data = {}

    if not hasattr(result, "pages") or not result.pages:
        logger.error(f"No page information available for rotation check: {filename}")
        return rotation_data

    for i, page in enumerate(result.pages):
        if hasattr(page, "angle"):
            rotation_angle = page.angle
            if rotation_angle != 0:
                logger.error(f"Page {i+1} is rotated by {rotation_angle} degrees")
                # Store page index as integer, not string
                rotation_data[i] = rotation_angle
            else:
                logger.error(f"Page {i+1} has no rotation (0 degrees)")
        else:
            logger.error(f"Page {i+1} rotation information not available")

    return rotation_data


@celery.task(base=BaseTaskWithRetry)
def process_with_azure_document_intelligence(filename: str, file_id: int = None):
    """
    Processes a PDF document using Azure Document Intelligence and overlays OCR text onto
    the local temporary file (stored under <workdir>/tmp).

    Steps:
      0. Verify the file meets Azure Document Intelligence service limits
      1. Uploads the document for OCR using Azure Document Intelligence.
      2. Retrieves the processed PDF with embedded text.
      3. Saves the OCR-processed PDF locally in the same location as before.
      4. Checks for page rotation and triggers page rotation if needed.
      5. Triggers downstream metadata extraction.

    Args:
        filename: Name of the file to process
        file_id: Optional file ID to pass through to subsequent tasks
    """
    try:
        tmp_file_path = os.path.join(settings.workdir, "tmp", filename)
        if not os.path.exists(tmp_file_path):
            raise FileNotFoundError(f"Local file not found: {tmp_file_path}")

        # Check file size against service limits
        file_size = os.path.getsize(tmp_file_path)
        if file_size > AZURE_DOC_INTELLIGENCE_LIMITS["max_file_size_bytes"]:
            error_msg = (
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds Azure Document Intelligence limit of 500 MB"
            )
            logger.error(error_msg)
            return {"error": error_msg, "file": filename, "status": "Failed - Size limit exceeded"}

        # For PDF files, check page count against service limits
        # "Fail open" approach: only reject if we're sure it exceeds the limit
        if filename.lower().endswith(".pdf"):
            page_count = get_pdf_page_count(tmp_file_path)
            if page_count is not None and page_count > AZURE_DOC_INTELLIGENCE_LIMITS["max_pages"]:
                error_msg = f"PDF page count ({page_count}) exceeds Azure Document Intelligence limit of 2000 pages"
                logger.error(error_msg)
                return {"error": error_msg, "file": filename, "status": "Failed - Page limit exceeded"}
            if page_count is None:
                logger.warning(f"Could not determine page count for {filename}, proceeding with processing anyway")

        logger.info(f"Processing {filename} with Azure Document Intelligence OCR.")

        # Open and send the document for processing
        with open(tmp_file_path, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-read", body=f, output=[AnalyzeOutputOption.PDF]
            )
        result: AnalyzeResult = poller.result()
        operation_id = poller.details["operation_id"]

        # Check and log page rotation information
        rotation_data = check_page_rotation(result, filename)

        # Retrieve the processed searchable PDF
        response = document_intelligence_client.get_analyze_result_pdf(model_id=result.model_id, result_id=operation_id)
        searchable_pdf_path = tmp_file_path  # Overwrite the original PDF location
        with open(searchable_pdf_path, "wb") as writer:
            writer.writelines(response)
        logger.info(f"Searchable PDF saved at: {searchable_pdf_path}")

        # Extract raw text content from the result
        extracted_text = result.content if result.content else ""
        logger.info(f"Extracted text for {filename}: {len(extracted_text)} characters")

        # Trigger page rotation task if rotation is detected, otherwise proceed to metadata extraction
        rotate_pdf_pages.delay(filename, extracted_text, rotation_data, file_id)

        return {"file": filename, "searchable_pdf": searchable_pdf_path, "cleaned_text": extracted_text}
    except Exception as e:
        logger.error(f"Error processing {filename} with Azure Document Intelligence: {e}")
        raise
