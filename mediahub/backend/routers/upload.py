from fastapi import APIRouter, HTTPException, UploadFile, File
from utils import (
    UPLOAD_DIR,
    ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES, ALLOWED_DOC_TYPES,
    MAX_IMAGE_SIZE, MAX_VIDEO_SIZE, MAX_DOC_SIZE,
)
import os, uuid

router = APIRouter()


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES | ALLOWED_DOC_TYPES:
        raise HTTPException(400, f"Неподдерживаемый тип файла: {content_type}")

    ext = (file.filename or "file").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    data = await file.read()
    if content_type in ALLOWED_VIDEO_TYPES:
        max_size = MAX_VIDEO_SIZE
    elif content_type in ALLOWED_DOC_TYPES:
        max_size = MAX_DOC_SIZE
    else:
        max_size = MAX_IMAGE_SIZE
    if len(data) > max_size:
        raise HTTPException(400, f"Файл слишком большой (макс. {max_size // 1024 // 1024} МБ)")

    with open(filepath, "wb") as f:
        f.write(data)

    if content_type in ALLOWED_VIDEO_TYPES:
        file_type = "video"
    elif content_type in ALLOWED_DOC_TYPES:
        file_type = "doc"
    else:
        file_type = "image"
    return {"url": f"/uploads/{filename}", "type": file_type, "filename": file.filename or filename}
