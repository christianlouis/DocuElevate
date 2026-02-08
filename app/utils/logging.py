from app.database import SessionLocal
from app.models import ProcessingLog


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
