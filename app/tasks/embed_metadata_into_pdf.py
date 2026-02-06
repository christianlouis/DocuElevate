#!/usr/bin/env python3

import os
import shutil
import tempfile
import PyPDF2  # Replace fitz with PyPDF2
import json
from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.tasks.finalize_document_storage import finalize_document_storage

# Import the shared Celery instance
from app.celery_app import celery

# Directory constants - defined here to avoid hardcoded strings (BAN-B108)
TMP_SUBDIR = "tmp"
PROCESSED_SUBDIR = "processed"

def unique_filepath(directory, base_filename, extension=".pdf"):
    """
    Returns a unique filepath in the specified directory.
    If 'base_filename.pdf' exists, it will append an underscore and counter.
    """
    candidate = os.path.join(directory, base_filename + extension)
    if not os.path.exists(candidate):
        return candidate
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{base_filename}_{counter}{extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def persist_metadata(metadata, final_pdf_path):
    """
    Saves the metadata dictionary to a JSON file with the same base name as the final PDF.
    For example, if final_pdf_path is "<workdir>/processed/MyFile.pdf",
    the metadata will be saved as "<workdir>/processed/MyFile.json".
    """
    base, _ = os.path.splitext(final_pdf_path)
    json_path = base + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    return json_path

@celery.task(base=BaseTaskWithRetry)
def embed_metadata_into_pdf(local_file_path: str, extracted_text: str, metadata: dict):
    """
    Embeds extracted metadata into the PDF's standard metadata fields.
    The mapping is as follows:
      - title: uses the extracted metadata "filename"
      - author: uses "absender" (or "Unknown" if missing)
      - subject: uses "document_type" (or "Unknown")
      - keywords: a comma‐separated list from the "tags" field

    After processing, the file is moved to
      <workdir>/processed/<suggested_filename.pdf>
    where <suggested_filename.pdf> is derived from metadata["filename"].
    Additionally, the metadata is persisted to a JSON file with the same base name.
    """
    # Check for file existence; if not found, try the known shared tmp directory.
    if not os.path.exists(local_file_path):
        alt_path = os.path.join(settings.workdir, TMP_SUBDIR, os.path.basename(local_file_path))
        if os.path.exists(alt_path):
            local_file_path = alt_path
        else:
            print(f"[ERROR] Local file {local_file_path} not found, cannot embed metadata.")
            return {"error": "File not found"}

    # Work on a safe copy in a secure temporary directory
    original_file = local_file_path
    # Create a temporary file with the same extension as the original
    _, ext = os.path.splitext(local_file_path)
    tmp_file = tempfile.NamedTemporaryFile(mode='wb', suffix=ext, prefix='processed_', delete=False)
    processed_file = tmp_file.name
    tmp_file.close()

    # Create a safe copy to work on
    shutil.copy(original_file, processed_file)

    try:
        print(f"[DEBUG] Embedding metadata into {processed_file}...")

        # Open the PDF and modify metadata
        with open(processed_file, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            pdf_writer = PyPDF2.PdfWriter()
            
            # Copy all pages from the reader to the writer
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
            
            # Set PDF metadata
            pdf_writer.add_metadata({
                "/Title": metadata.get("filename", "Unknown Document"),
                "/Author": metadata.get("absender", "Unknown"),
                "/Subject": metadata.get("document_type", "Unknown"),
                "/Keywords": ", ".join(metadata.get("tags", []))
            })
            
            # Write the modified PDF
            with open(processed_file, 'wb') as output_file:
                pdf_writer.write(output_file)

        print(f"[INFO] Metadata embedded successfully in {processed_file}")

        # Use the suggested filename from metadata; if not provided, use the original basename.
        suggested_filename = metadata.get("filename", os.path.splitext(os.path.basename(local_file_path))[0])
        # Remove any extension and then add .pdf
        suggested_filename = os.path.splitext(suggested_filename)[0]
        # Define the final directory based on settings.workdir and ensure it exists.
        final_dir = os.path.join(settings.workdir, PROCESSED_SUBDIR)
        os.makedirs(final_dir, exist_ok=True)
        # Get a unique filepath in case of collisions.
        final_file_path = unique_filepath(final_dir, suggested_filename, extension=".pdf")

        # Move the processed file using shutil.move to handle cross-device moves.
        shutil.move(processed_file, final_file_path)
        # Ensure the temporary file is deleted if it still exists.
        if os.path.exists(processed_file):
            os.remove(processed_file)

        # Persist the metadata into a JSON file with the same base name.
        json_path = persist_metadata(metadata, final_file_path)
        print(f"[INFO] Metadata persisted to {json_path}")

        # Trigger the next step: final storage.
        finalize_document_storage.delay(original_file, final_file_path, metadata)

        # After triggering final storage, delete the original file if it is in workdir/tmp.
        workdir_tmp = os.path.join(settings.workdir, TMP_SUBDIR)
        if original_file.startswith(workdir_tmp) and os.path.exists(original_file):
            try:
                os.remove(original_file)
                print(f"[INFO] Deleted original file from {original_file}")
            except Exception as e:
                print(f"[ERROR] Could not delete original file {original_file}: {e}")

        return {"file": final_file_path, "metadata_file": json_path, "status": "Metadata embedded"}

    except Exception as e:
        print(f"[ERROR] Failed to embed metadata into {processed_file}: {e}")
        # Clean up temporary file in case of error
        if os.path.exists(processed_file):
            try:
                os.remove(processed_file)
                print(f"[INFO] Cleaned up temporary file {processed_file}")
            except Exception as cleanup_error:
                print(f"[ERROR] Could not clean up temporary file {processed_file}: {cleanup_error}")
        return {"error": str(e)}
