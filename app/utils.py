# app/utils.py
import hashlib
from app.database import SessionLocal
from app.models import ProcessingLog

def hash_file(filepath, chunk_size=65536):
    """
    Returns the SHA-256 hash of the file at 'filepath'.
    Reads the file in chunks to handle large files efficiently.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()
    return sha256.hexdigest()


def log_task_progress(task_id, step_name, status, message=None, file_id=None):
def log_task_progress(task_id, step_name, status, message=None, file_id=None):
    """
    Logs the progress of a Celery task to the database.
    """
    with SessionLocal() as db:
        log_entry = ProcessingLog(
            task_id=task_id,
            step_name=step_name,
            status=status,
            message=message,
            file_id=file_id,
        )
        db.add(log_entry)
        db.commit()
