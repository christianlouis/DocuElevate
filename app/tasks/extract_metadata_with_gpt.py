#!/usr/bin/env python3

import json
import logging
import os
import re

import openai

# Import the shared Celery instance
from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils import log_task_progress

logger = logging.getLogger(__name__)

# Initialize OpenAI client dynamically with better error handling
try:
    client = openai.OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    client = None


def extract_json_from_text(text):
    """
    Try to extract a JSON object from the text.
    - First, check for a JSON block inside triple backticks.
    - If not found, try to extract text from the first '{' to the last '}'.
    """
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
    return None


@celery.task(base=BaseTaskWithRetry, bind=True)
def extract_metadata_with_gpt(self, filename: str, cleaned_text: str, file_id: int = None):
    """
    Uses OpenAI to classify document metadata.
    
    Args:
        filename: Can be either a basename (e.g., "file.pdf") or a full path (e.g., "/workdir/processed/file.pdf")
        cleaned_text: The extracted text from the document
        file_id: Optional file ID for tracking
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting metadata extraction for: {filename}")
    log_task_progress(
        task_id, "extract_metadata_with_gpt", "in_progress", f"Extracting metadata for {os.path.basename(filename)}", file_id=file_id
    )

    # Get file_id from database if not provided
    if file_id is None:
        tmp_dir = os.path.join(settings.workdir, "tmp")
        # Handle both basename and full path
        if os.path.isabs(filename):
            file_path = filename
        else:
            file_path = os.path.join(tmp_dir, filename)
        if os.path.exists(file_path):
            with SessionLocal() as db:
                file_record = db.query(FileRecord).filter_by(local_filename=file_path).first()
                if file_record:
                    file_id = file_record.id

    prompt = (
        "You are a specialized document analyzer trained to extract structured metadata from documents.\n"
        "Your task is to analyze the given text and return a well-structured JSON object.\n\n"
        "Extract and return the following fields:\n"
        "1. **filename**: Machine-readable filename "
        "(YYYY-MM-DD_DescriptiveTitle, use only letters, numbers, periods, and underscores).\n"
        '2. **empfaenger**: The recipient, or "Unknown" if not found.\n'
        '3. **absender**: The sender, or "Unknown" if not found.\n'
        "4. **correspondent**: The entity or company that issued the document "
        '(shortest possible name, e.g., "Amazon" instead of "Amazon EU SARL, German branch").\n'
        "5. **kommunikationsart**: One of [Behoerdlicher_Brief, Rechnung, Kontoauszug, Vertrag, "
        "Quittung, Privater_Brief, Einladung, Gewerbliche_Korrespondenz, Newsletter, Werbung, Sonstiges].\n"
        "6. **kommunikationskategorie**: One of [Amtliche_Postbehoerdliche_Dokumente, "
        "Finanz_und_Vertragsdokumente, Geschaeftliche_Kommunikation, "
        "Private_Korrespondenz, Sonstige_Informationen].\n"
        "7. **document_type**: Precise classification (e.g., Invoice, Contract, Information, Unknown).\n"
        "8. **tags**: A list of up to 4 relevant thematic keywords.\n"
        '9. **language**: Detected document language (ISO 639-1 code, e.g., "de" or "en").\n'
        "10. **title**: A human-readable title summarizing the document content.\n"
        "11. **confidence_score**: A numeric value (0-100) indicating the confidence level "
        "of the extracted metadata.\n"
        "12. **reference_number**: Extracted invoice/order/reference number if available.\n"
        "13. **monetary_amounts**: A list of key monetary values detected in the document.\n\n"
        "### Important Rules:\n"
        "- **OCR Correction**: Assume the text has been corrected for OCR errors.\n"
        "- **Tagging**: Max 4 tags, avoiding generic or overly specific terms.\n"
        "- **Title**: Concise, no addresses, and contains key identifying features.\n"
        "- **Date Selection**: Use the most relevant date if multiple are found.\n"
        "- **Output Language**: Maintain the document's original language.\n\n"
        f"Extracted text:\n{cleaned_text}\n\n"
        "Return only valid JSON with no additional commentary.\n"
    )

    try:
        logger.info(f"[{task_id}] Sending classification request for {filename}...")
        log_task_progress(task_id, "call_openai", "in_progress", "Calling OpenAI API", file_id=file_id)
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are an intelligent document classifier."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        content = completion.choices[0].message.content
        logger.info(f"[{task_id}] Raw classification response for {filename}: {content[:200]}...")
        log_task_progress(
            task_id,
            "call_openai",
            "success",
            "Received OpenAI response",
            file_id=file_id,
            detail=f"Raw classification response:\n{content}",
        )

        json_text = extract_json_from_text(content)
        if not json_text:
            logger.error(f"[{task_id}] Could not find valid JSON in GPT response for {filename}.")
            log_task_progress(
                task_id,
                "extract_metadata_with_gpt",
                "failure",
                "Invalid JSON in response",
                file_id=file_id,
                detail=f"Could not parse valid JSON from GPT response.\nRaw response:\n{content}",
            )
            return {}

        metadata = json.loads(json_text)

        # SECURITY: Validate filename format from GPT to prevent path traversal
        # The prompt requests filenames with only letters, numbers, periods, and underscores
        # Enforce this constraint to prevent malicious filenames
        suggested_filename = metadata.get("filename", "")
        if suggested_filename:
            # Check if filename contains only safe characters AND explicitly check for ".."
            # Defense in depth: While the regex [\w\-\. ]+ already excludes / and \,
            # we explicitly reject ".." to guard against:
            # 1. Potential locale-specific \w behavior
            # 2. Files literally named ".." which are valid but problematic
            # 3. Future code changes that might relax the regex
            if not re.match(r"^[\w\-\. ]+$", suggested_filename) or ".." in suggested_filename:
                logger.warning(f"[{task_id}] Invalid filename format from GPT: '{suggested_filename}', using fallback")
                # Reset to empty to trigger fallback to original filename
                metadata["filename"] = ""

        logger.info(f"[{task_id}] Extracted metadata: {metadata}")
        log_task_progress(
            task_id,
            "parse_metadata",
            "success",
            f"Parsed metadata: {list(metadata.keys())}",
            file_id=file_id,
            detail=f"Extracted metadata:\n{json.dumps(metadata, ensure_ascii=False, indent=2)}",
        )

        # Trigger the next step: embedding metadata into the PDF
        # Pass the filename (can be basename or full path) so embed_metadata_into_pdf can find the file on disk
        logger.info(f"[{task_id}] Queueing metadata embedding task")
        log_task_progress(
            task_id, "extract_metadata_with_gpt", "success", "Metadata extracted, queuing embed task", file_id=file_id
        )
        embed_metadata_into_pdf.delay(filename, cleaned_text, metadata, file_id)

        return {"s3_file": os.path.basename(filename), "metadata": metadata}

    except Exception as e:
        logger.exception(f"[{task_id}] OpenAI classification failed for {filename}: {e}")
        log_task_progress(
            task_id,
            "extract_metadata_with_gpt",
            "failure",
            f"Exception: {str(e)}",
            file_id=file_id,
            detail=f"OpenAI classification failed for {filename}.\nException: {str(e)}",
        )
        return {}
