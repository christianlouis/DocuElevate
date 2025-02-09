#!/usr/bin/env python3

from fastapi import FastAPI, Depends
from .config import settings
from .database import engine, SessionLocal
from .models import Base
from .tasks import process_document

app = FastAPI(title="Document Processor")

# Initialize database
Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"message": "Document Processing API"}

@app.post("/process/")
def process(file_path: str):
    """Trigger document processing"""
    task = process_document.delay(file_path)
    return {"task_id": task.id, "status": "queued"}
