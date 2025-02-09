#!/usr/bin/env python3

import boto3
from .celery_worker import celery
from .config import settings

textract_client = boto3.client(
    "textract",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

@celery.task
def process_document(file_path: str):
    """Process document: OCR, metadata extraction, upload"""
    
    # Send to AWS Textract
    with open(file_path, "rb") as document:
        response = textract_client.analyze_document(
            Document={"Bytes": document.read()},
            FeatureTypes=["TABLES", "FORMS"]
        )
    
    extracted_text = " ".join([block["Text"] for block in response["Blocks"] if block["BlockType"] == "WORD"])
    
    return {"file": file_path, "text": extracted_text}
