# Import tasks so they can be discovered by Celery
from app.tasks.process_document import process_document
from app.tasks.process_with_azure_document_intelligence import process_with_azure_document_intelligence
