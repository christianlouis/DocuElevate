# In main.py or a new dedicated file, e.g. app/routes_ui.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.tasks.upload_to_s3 import upload_to_s3
import os

router = APIRouter()

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

# Then include this in your main app as well:
#   app.include_router(router)
