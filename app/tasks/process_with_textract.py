import time
import os
import boto3
import fitz  # PyMuPDF
import logging

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
from app.celery_app import celery

logger = logging.getLogger(__name__)

# Initialize AWS clients using settings.
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)
textract_client = boto3.client(
    "textract",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

BUCKET_NAME = settings.s3_bucket_name

def create_searchable_pdf(tmp_file_path, extracted_pages):
    """
    Opens the PDF at tmp_file_path, overlays invisible OCR text using the
    Textract bounding box data (extracted_pages), and overwrites the same file.
    
    extracted_pages: list of pages; each page is a list of (text, bbox) tuples.
    """
    pdf_doc = fitz.open(tmp_file_path)
    try:
        for page_num, page in enumerate(pdf_doc):
            if page_num < len(extracted_pages):
                for line, bbox in extracted_pages[page_num]:
                    # Convert relative bbox to absolute coordinates.
                    rect = fitz.Rect(
                        bbox['Left'] * page.rect.width,
                        bbox['Top'] * page.rect.height,
                        (bbox['Left'] + bbox['Width']) * page.rect.width,
                        (bbox['Top'] + bbox['Height']) * page.rect.height,
                    )
                    page.insert_text(
                        rect.bl,          # starting at the bottom-left of the bbox
                        line,
                        fontsize=12,      # adjust as needed
                        fontname="helv",  # Helvetica
                        color=(1, 1, 1, 0),  # transparent
                        render_mode=3     # invisible but searchable text
                    )
        # Overwrite the same file.
        pdf_doc.save(tmp_file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        logger.info(f"Overwritten tmp file with OCR overlay: {tmp_file_path}")
    finally:
        pdf_doc.close()

@celery.task(base=BaseTaskWithRetry)
def process_with_textract(s3_filename: str):
    """
    Processes a PDF document using Textract and overlays invisible OCR text onto
    the local temporary file (already stored under /var/docparse/working/tmp).
    
    Steps:
      1. Start a Textract text detection job.
      2. Poll until the job succeeds and organize the Textract Blocks into pages
         (each page is a list of (text, bounding-box) tuples).
      3. Use the local tmp file at /var/docparse/working/tmp/<s3_filename> to add the OCR overlay.
      4. Delete the S3 object.
      5. Trigger downstream metadata extraction by calling extract_metadata_with_gpt.
    """
    try:
        logger.info(f"Starting Textract job for {s3_filename}")
        response = textract_client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": BUCKET_NAME, "Name": s3_filename}}
        )
        job_id = response["JobId"]
        logger.info(f"Textract job started, JobId: {job_id}")

        # Process Textract Blocks into pages.
        extracted_pages = []
        current_page_lines = []
        while True:
            result = textract_client.get_document_text_detection(JobId=job_id)
            status = result["JobStatus"]
            if status == "SUCCEEDED":
                logger.info("Textract job succeeded.")
                for block in result["Blocks"]:
                    if block["BlockType"] == "PAGE":
                        if current_page_lines:
                            extracted_pages.append(current_page_lines)
                            current_page_lines = []
                    elif block["BlockType"] == "LINE":
                        bbox = block["Geometry"]["BoundingBox"]
                        current_page_lines.append((block["Text"], bbox))
                if current_page_lines:
                    extracted_pages.append(current_page_lines)
                break
            elif status in ["FAILED", "PARTIAL_SUCCESS"]:
                logger.error("Textract job failed.")
                raise Exception("Textract job failed")
            time.sleep(3)

        # Use the existing local tmp file (from /var/docparse/working/tmp).
        tmp_file_path = os.path.join("/var/docparse/working/tmp", s3_filename)
        if not os.path.exists(tmp_file_path):
            raise Exception(f"Local file not found: {tmp_file_path}")
        logger.info(f"Processing local file {tmp_file_path} with OCR overlay.")

        # Overwrite the tmp file with the added OCR overlay.
        create_searchable_pdf(tmp_file_path, extracted_pages)

        # Delete the S3 object.
        logger.info(f"Deleting {s3_filename} from S3")
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_filename)

        # Concatenate extracted text.
        cleaned_text = " ".join([line for page in extracted_pages for line, _ in page])
        # Trigger downstream metadata extraction.
        extract_metadata_with_gpt.delay(s3_filename, cleaned_text)

        return {"s3_file": s3_filename, "searchable_pdf": tmp_file_path, "cleaned_text": cleaned_text}
    except Exception as e:
        logger.error(f"Error processing {s3_filename}: {e}")
        raise

