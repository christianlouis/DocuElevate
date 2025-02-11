#!/usr/bin/env python3

import os
from fastapi import FastAPI, HTTPException
from app.config import settings
from app.tasks.upload_to_s3 import upload_to_s3

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
