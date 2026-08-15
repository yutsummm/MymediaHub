import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from utils import (
    ALLOWED_DOC_TYPES,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_VIDEO_TYPES,
    MAX_DOC_SIZE,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    UPLOAD_DIR,
    get_current_user_id,
    sign_upload_url,
)

router = APIRouter()


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
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
    # Ссылку отдаём подписанной, чтобы предпросмотр в редакторе открылся сразу.
    # В базу она попадёт уже без подписи — через media_for_storage.
    return {
        "url": sign_upload_url(f"/uploads/{filename}"),
        "type": file_type,
        "filename": file.filename or filename,
    }
