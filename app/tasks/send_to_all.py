# app/tasks/send_to_all.py

from app.celery_app import celery
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_paperless import upload_to_paperless

@celery.task
def send_to_all_destinations(file_path: str):
    """
    Fires off tasks to upload a single file to Dropbox, Nextcloud, and Paperless.
    These tasks run in parallel (Celery returns immediately from each .delay()).
    """
    upload_to_dropbox.delay(file_path)
    upload_to_nextcloud.delay(file_path)
    upload_to_paperless.delay(file_path)

    return {
        "status": "All upload tasks enqueued",
        "file_path": file_path
    }
