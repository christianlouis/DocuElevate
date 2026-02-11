from app.database import SessionLocal
from app.models import ProcessingLog


def log_task_progress(task_id, step_name, status, message=None, file_id=None, detail=None):
    """
    Logs the progress of a Celery task to the database.

    Args:
        task_id: The Celery task ID
        step_name: Name of the processing step
        status: Current status (pending, in_progress, success, failure)
        message: Short summary message
        file_id: Optional associated file record ID
        detail: Optional verbose log output for diagnostics
    """
    with SessionLocal() as db:
        log_entry = ProcessingLog(
            task_id=task_id,
            step_name=step_name,
            status=status,
            message=message,
            file_id=file_id,
            detail=detail,
        )
        db.add(log_entry)
        db.commit()
