#!/usr/bin/env python3

from app.config import settings
import openai
from app.tasks.retry_config import BaseTaskWithRetry

# Import the shared Celery instance
from app.celery_app import celery

# Initialize OpenAI client dynamically
client = openai.OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url
)

@celery.task(base=BaseTaskWithRetry)
def refine_text_with_gpt(filename: str, raw_text: str):
    """Uses OpenAI to clean and refine OCR text."""
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "Clean and format the following text. The idea is that the text you see comes from an OCR system and your task is to eliminate OCR errors. Keep the original language when doing so."},
            {"role": "user", "content": raw_text}
        ]
    )
    
    cleaned_text = response.choices[0].message.content

    # Trigger next task (import locally if needed to avoid circular imports)
    from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt
    extract_metadata_with_gpt.delay(filename, cleaned_text)

    return {"s3_file": filename, "cleaned_text": cleaned_text}

