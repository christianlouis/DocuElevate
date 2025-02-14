import os
import logging
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

@celery.task(base=BaseTaskWithRetry)
def process_with_textract(s3_filename: str):
    """
    Processes a PDF document using Azure Document Intelligence and overlays OCR text onto
    the local temporary file (stored under <workdir>/tmp).
    
    Steps:
      1. Uploads the document for OCR using Azure Document Intelligence.
      2. Retrieves the processed PDF with embedded text.
      3. Saves the OCR-processed PDF locally in the same location as before.
      4. Extracts the text content for metadata processing.
      5. Triggers downstream metadata extraction by calling extract_metadata_with_gpt.
    """
    try:
        tmp_file_path = os.path.join(settings.workdir, "tmp", s3_filename)
        if not os.path.exists(tmp_file_path):
            raise FileNotFoundError(f"Local file not found: {tmp_file_path}")

        logger.info(f"Processing {s3_filename} with Azure Document Intelligence OCR.")

        # Open and send the document for processing
        with open(tmp_file_path, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-read", body=f, output=[AnalyzeOutputOption.PDF]
            )
        result: AnalyzeResult = poller.result()
        operation_id = poller.details["operation_id"]

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
        logger.info(f"Extracted text for {s3_filename}: {len(extracted_text)} characters")

        # Trigger downstream metadata extraction
        extract_metadata_with_gpt.delay(s3_filename, extracted_text)

        return {"s3_file": s3_filename, "searchable_pdf": searchable_pdf_path, "cleaned_text": extracted_text}
    except Exception as e:
        logger.error(f"Error processing {s3_filename} with Azure Document Intelligence: {e}")
        raise
