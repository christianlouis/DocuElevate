#!/usr/bin/env python3

import json
import re
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf

# Import the shared Celery instance
from app.celery_app import celery
import openai
import logging

logger = logging.getLogger(__name__)

# Initialize OpenAI client dynamically with better error handling
try:
    client = openai.OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url
    )
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
            return text[start:end+1]
    return None

@celery.task(base=BaseTaskWithRetry)
def extract_metadata_with_gpt(filename: str, cleaned_text: str):
    """Uses OpenAI to classify document metadata."""
    prompt = f"""
You are a specialized document analyzer trained to extract structured metadata from documents.
Your task is to analyze the given text and return a well-structured JSON object.

Extract and return the following fields:
1. **filename**: Machine-readable filename (YYYY-MM-DD_DescriptiveTitle, use only letters, numbers, periods, and underscores).
2. **empfaenger**: The recipient, or "Unknown" if not found.
3. **absender**: The sender, or "Unknown" if not found.
4. **correspondent**: The entity or company that issued the document (shortest possible name, e.g., "Amazon" instead of "Amazon EU SARL, German branch").
5. **kommunikationsart**: One of [Behoerdlicher_Brief, Rechnung, Kontoauszug, Vertrag, Quittung, Privater_Brief, Einladung, Gewerbliche_Korrespondenz, Newsletter, Werbung, Sonstiges].
6. **kommunikationskategorie**: One of [Amtliche_Postbehoerdliche_Dokumente, Finanz_und_Vertragsdokumente, Geschaeftliche_Kommunikation, Private_Korrespondenz, Sonstige_Informationen].
7. **document_type**: Precise classification (e.g., Invoice, Contract, Information, Unknown).
8. **tags**: A list of up to 4 relevant thematic keywords.
9. **language**: Detected document language (ISO 639-1 code, e.g., "de" or "en").
10. **title**: A human-readable title summarizing the document content.
11. **confidence_score**: A numeric value (0-100) indicating the confidence level of the extracted metadata.
12. **reference_number**: Extracted invoice/order/reference number if available.
13. **monetary_amounts**: A list of key monetary values detected in the document.

### Important Rules:
- **OCR Correction**: Assume the text has been corrected for OCR errors.
- **Tagging**: Max 4 tags, avoiding generic or overly specific terms.
- **Title**: Concise, no addresses, and contains key identifying features.
- **Date Selection**: Use the most relevant date if multiple are found.
- **Output Language**: Maintain the document's original language.

Extracted text:
{cleaned_text}

Return only valid JSON with no additional commentary.
"""

    try:
        print(f"[DEBUG] Sending classification request for {filename}...")
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are an intelligent document classifier."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        content = completion.choices[0].message.content
        print(f"[DEBUG] Raw classification response for {filename}: {content}")

        json_text = extract_json_from_text(content)
        if not json_text:
            print(f"[ERROR] Could not find valid JSON in GPT response for {filename}.")
            return {}

        metadata = json.loads(json_text)
        print(f"[DEBUG] Extracted metadata: {metadata}")

        # Trigger the next step: embedding metadata into the PDF
        embed_metadata_into_pdf.delay(filename, cleaned_text, metadata)

        return {"s3_file": filename, "metadata": metadata}

    except Exception as e:
        print(f"[ERROR] OpenAI classification failed for {filename}: {e}")
        return {}
