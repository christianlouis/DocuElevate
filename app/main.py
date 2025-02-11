#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException
from .tasks.upload_to_s3 import upload_to_s3
import os

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

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File {file_path} not found.")

    task = upload_to_s3.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

