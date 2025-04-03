import os
import logging
import PyPDF2
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeOutputOption, AnalyzeResult

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery

logger = logging.getLogger(__name__)

# Initialize Azure Document Intelligence client
document_intelligence_client = DocumentIntelligenceClient(
    endpoint=settings.azure_endpoint,
    credential=AzureKeyCredential(settings.azure_ai_key)
)

# Azure Document Intelligence service limits for Standard S0 tier
AZURE_DOC_INTELLIGENCE_LIMITS = {
    "max_file_size_bytes": 500 * 1024 * 1024,  # 500 MB
    "max_pages": 2000,
}

def get_pdf_page_count(file_path):
    """Get the number of pages in a PDF file."""
    try:
        with open(file_path, 'rb') as file:
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
    """
    logger.error(f"Checking rotation for document: {filename}")
    
    if not hasattr(result, 'pages') or not result.pages:
        logger.error(f"No page information available for rotation check: {filename}")
        return
        
    for i, page in enumerate(result.pages):
        if hasattr(page, 'angle'):
            rotation_angle = page.angle
            if rotation_angle != 0:
                logger.error(f"Page {i+1} is rotated by {rotation_angle} degrees")
            else:
                logger.error(f"Page {i+1} has no rotation (0 degrees)")
        else:
            logger.error(f"Page {i+1} rotation information not available")

@celery.task(base=BaseTaskWithRetry)
def process_with_azure_document_intelligence(filename: str):
    """
    Processes a PDF document using Azure Document Intelligence and overlays OCR text onto
    the local temporary file (stored under <workdir>/tmp).
    
    Steps:
      0. Verify the file meets Azure Document Intelligence service limits
      1. Uploads the document for OCR using Azure Document Intelligence.
      2. Retrieves the processed PDF with embedded text.
      3. Saves the OCR-processed PDF locally in the same location as before.
      4. Extracts the text content for metadata processing.
      5. Triggers downstream metadata extraction by calling extract_metadata_with_gpt.
    """
    try:
        tmp_file_path = os.path.join(settings.workdir, "tmp", filename)
        if not os.path.exists(tmp_file_path):
            raise FileNotFoundError(f"Local file not found: {tmp_file_path}")

        # Check file size against service limits
        file_size = os.path.getsize(tmp_file_path)
        if file_size > AZURE_DOC_INTELLIGENCE_LIMITS["max_file_size_bytes"]:
            error_msg = f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds Azure Document Intelligence limit of 500 MB"
            logger.error(error_msg)
            return {"error": error_msg, "file": filename, "status": "Failed - Size limit exceeded"}

        # For PDF files, check page count against service limits
        # "Fail open" approach: only reject if we're sure it exceeds the limit
        if filename.lower().endswith('.pdf'):
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
        check_page_rotation(result, filename)

        # Retrieve the processed searchable PDF
        response = document_intelligence_client.get_analyze_result_pdf(
            model_id=result.model_id, result_id=operation_id
        )
        searchable_pdf_path = tmp_file_path  # Overwrite the original PDF location
        with open(searchable_pdf_path, "wb") as writer:
            writer.writelines(response)
        logger.info(f"Searchable PDF saved at: {searchable_pdf_path}")

        # Extract raw text content from the result
        extracted_text = result.content if result.content else ""
        logger.info(f"Extracted text for {filename}: {len(extracted_text)} characters")

        # Trigger downstream metadata extraction
        extract_metadata_with_gpt.delay(filename, extracted_text)

        return {"file": filename, "searchable_pdf": searchable_pdf_path, "cleaned_text": extracted_text}
    except Exception as e:
        logger.error(f"Error processing {filename} with Azure Document Intelligence: {e}")
        raise
