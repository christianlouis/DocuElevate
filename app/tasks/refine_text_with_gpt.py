#!/usr/bin/env python3

from app.config import settings
from openai import OpenAI
from app.tasks.retry_config import BaseTaskWithRetry

# Import the shared Celery instance
from app.celery_app import celery



client = OpenAI(api_key=settings.openai_api_key)

@celery.task(base=BaseTaskWithRetry)
def refine_text_with_gpt(s3_filename: str, raw_text: str):
    """Uses GPT to clean and refine OCR text."""
    
    # Use the Chat Completions endpoint with 'messages'
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Clean and format the following text. The idea is that the text you see comes from an OCR system and your task is to eliminate OCR errors. Keep the original language when doing so."},
            {"role": "user", "content": raw_text}
        ]
    )
    
    cleaned_text = response.choices[0].message.content

    # Trigger next task (import locally if needed to avoid circular imports)
    from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
    extract_metadata_with_gpt.delay(s3_filename, cleaned_text)

    return {"s3_file": s3_filename, "cleaned_text": cleaned_text}

