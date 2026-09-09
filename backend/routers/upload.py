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
    UPLOAD_EXTENSIONS,
    check_rate_limit,
    get_current_user_id,
    get_db,
    sign_upload_url,
    upload_allowance,
)

router = APIRouter()

# Размер куска при записи на диск. От него зависит расход памяти на одну
# загрузку — и только он: сам файл в память целиком больше не попадает.
CHUNK_SIZE = 1024 * 1024


def _limit_for(content_type: str) -> tuple[int, str]:
    """Предел размера и вид файла для проверенного типа содержимого."""
    if content_type in ALLOWED_VIDEO_TYPES:
        return MAX_VIDEO_SIZE, "video"
    if content_type in ALLOWED_DOC_TYPES:
        return MAX_DOC_SIZE, "doc"
    return MAX_IMAGE_SIZE, "image"


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    try:
        max_uploads, window = upload_allowance(user_id, conn)
    finally:
        conn.close()
    check_rate_limit(f"upload:{user_id}", max_uploads, window)

    # Заголовок может прийти с довеском вроде «; charset=...» — сравниваем
    # только сам тип, иначе годный файл отвергается из-за оформления заголовка.
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES | ALLOWED_DOC_TYPES:
        raise HTTPException(400, f"Неподдерживаемый тип файла: {content_type or 'неизвестен'}")

    max_size, file_type = _limit_for(content_type)
    # Расширение — из проверенного типа, а не из имени, которое дал человек:
    # имя `photo.html` при объявленном image/jpeg клало на диск веб-страницу,
    # и она отдавалась браузером как страница, на нашем домене.
    filename = f"{uuid.uuid4().hex}.{UPLOAD_EXTENSIONS[content_type]}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    # Пишем кусками и обрываем, как только предел превышен. Раньше файл сначала
    # читался в память целиком и лишь потом сверялся с пределом: три ролика по
    # сотне мегабайт разом — это триста мегабайт сверх обычной работы, а вместе
    # с процессом падали публикации, планировщик и сбор обращений.
    written = 0
    try:
        with open(filepath, "wb") as f:
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_size:
                    raise HTTPException(
                        400, f"Файл слишком большой (макс. {max_size // 1024 // 1024} МБ)")
                f.write(chunk)
    except BaseException:
        # Недописанный файл на диске не нужен никому и никогда: ссылки на него
        # не существует, а место он занимает.
        try:
            os.remove(filepath)
        except OSError:
            pass
        raise

    if written == 0:
        try:
            os.remove(filepath)
        except OSError:
            pass
        raise HTTPException(400, "Файл пуст")

    # Ссылку отдаём подписанной, чтобы предпросмотр в редакторе открылся сразу.
    # В базу она попадёт уже без подписи — через media_for_storage.
    return {
        "url": sign_upload_url(f"/uploads/{filename}"),
        "type": file_type,
        "filename": file.filename or filename,
    }
