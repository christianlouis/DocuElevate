#!/usr/bin/env python3

import json
import re
from openai import OpenAI
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.embed_metadata_into_pdf import embed_metadata_into_pdf

# Import the shared Celery instance
from app.celery_app import celery

client = OpenAI(api_key=settings.openai_api_key)

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
def extract_metadata_with_gpt(s3_filename: str, cleaned_text: str):
    """Uses OpenAI GPT-4o to classify document metadata."""
    
    prompt = f"""
You are an intelligent document classifier.
Given the following extracted text from a document, analyze it and return a JSON object with the following fields:
1. "filename": A machine-readable filename in the format YYYY-MM-DD_DescriptiveTitle (use only letters, numbers, periods, and underscores).
2. "empfaenger": The recipient, or "Unknown" if not found.
3. "absender": The sender, or "Unknown" if not found.
4. "correspondent": A correspondent extracted from the document, or "Unknown".
5. "kommunikationsart": One of [Behoerdlicher_Brief, Rechnung, Kontoauszug, Vertrag, Quittung, Privater_Brief, Einladung, Gewerbliche_Korrespondenz, Newsletter, Werbung, Sonstiges].
6. "kommunikationskategorie": One of [Amtliche_Postbehoerdliche_Dokumente, Finanz_und_Vertragsdokumente, Geschaeftliche_Kommunikation, Private_Korrespondenz, Sonstige_Informationen].
7. "document_type": The document type, or "Unknown".
8. "tags": A list of additional keywords extracted from the document.
9. "language": The detected language code (e.g., "DE").
10. "title": A human-friendly title for the document.

Extracted text:
{cleaned_text}

Return only valid JSON with no additional commentary.
"""

    try:
        print(f"[DEBUG] Sending classification request for {s3_filename}...")
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an intelligent document classifier."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        content = completion.choices[0].message.content
        print(f"[DEBUG] Raw classification response for {s3_filename}: {content}")

        json_text = extract_json_from_text(content)
        if not json_text:
            print(f"[ERROR] Could not find valid JSON in GPT response for {s3_filename}.")
            return {}

        metadata = json.loads(json_text)
        print(f"[DEBUG] Extracted metadata: {metadata}")

        # Trigger the next step: embedding metadata into the PDF
        embed_metadata_into_pdf.delay(s3_filename, cleaned_text, metadata)

        return {"s3_file": s3_filename, "metadata": metadata}

    except Exception as e:
        print(f"[ERROR] OpenAI classification failed for {s3_filename}: {e}")
        return {}

