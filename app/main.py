#!/usr/bin/env python3

import os
from fastapi import FastAPI, HTTPException
from app.config import settings
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.send_to_all import send_to_all_destinations
from app.frontend import router as frontend_router

app = FastAPI(title="Document Processing API")

@app.get("/")
def root():
    return {"message": "Document Processing API"}

@app.post("/process/")
def process(file_path: str):
    """
    API Endpoint to start document processing.
    This enqueues the first task (upload_to_s3), which handles the full pipeline.
    """

    # If file_path is not absolute, treat it as relative to settings.workdir.
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")

    task = upload_to_s3.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@app.post("/send_to_dropbox/")
def send_to_dropbox(file_path: str):
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_dropbox.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@app.post("/send_to_paperless/")
def send_to_paperless(file_path: str):
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_paperless.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@app.post("/send_to_nextcloud/")
def send_to_nextcloud(file_path: str):
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")
    task = upload_to_nextcloud.delay(file_path)
    return {"task_id": task.id, "status": "queued"}


@app.post("/send_to_all_destinations/")
def send_to_all_destinations_endpoint(file_path: str):
    """
    Call the aggregator task that sends this file to dropbox, nextcloud, and paperless.
    """
    if not os.path.isabs(file_path):
        # If not absolute, assume it's in processed subdir
        file_path = os.path.join(settings.workdir, 'processed', file_path)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400,
            detail=f"File {file_path} not found."
        )

    task = send_to_all_destinations.delay(file_path)
    return {"task_id": task.id, "status": "queued", "file_path": file_path}



@app.post("/processall")
def process_all_pdfs_in_workdir():
    """
    Finds all .pdf files in <workdir>/processed
    and enqueues them for upload_to_s3.
    """
    target_dir = settings.workdir
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory {target_dir} does not exist.")

    pdf_files = []
    for filename in os.listdir(target_dir):
        if filename.lower().endswith(".pdf"):
            pdf_files.append(filename)

    if not pdf_files:
        return {"message": "No PDF files found in processed directory."}

    task_ids = []
    for pdf in pdf_files:
        file_path = os.path.join(target_dir, pdf)
        # Enqueue upload_to_s3
        from app.tasks.upload_to_s3 import upload_to_s3
        task = upload_to_s3.delay(file_path)
        task_ids.append(task.id)

    return {
        "message": f"Enqueued {len(pdf_files)} PDFs to upload_to_s3",
        "pdf_files": pdf_files,
        "task_ids": task_ids
    }

app.include_router(frontend_router)

@router.post("/ui-upload")
async def ui_upload(file: UploadFile = File(...)):
    # You can store this file in your 'workdir' (like how /process does) or a tmp dir
    workdir = "/workdir"
    target_path = os.path.join(workdir, file.filename)

    try:
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Now you can call your existing Celery flow:
    task = upload_to_s3.delay(target_path)
    return {"task_id": task.id, "status": "queued"}