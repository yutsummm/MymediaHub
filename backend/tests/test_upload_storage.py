"""
Каталог загрузок должен настраиваться извне.

На Railway диск контейнера пересоздаётся при каждой выкатке, и все картинки и
видео постов исчезали. Лечится смонтированным томом, но для этого путь нельзя
намертво прибивать к каталогу с кодом.
"""
import io
import os
import subprocess
import sys

from conftest import auth

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def upload_dir_with_env(env_value: str | None) -> str:
    """Читает utils.UPLOAD_DIR в отдельном процессе — путь берётся на импорте."""
    env = dict(os.environ)
    env.pop("UPLOAD_DIR", None)
    if env_value is not None:
        env["UPLOAD_DIR"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", "import utils; print(utils.UPLOAD_DIR)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_upload_dir_defaults_next_to_code():
    expected = os.path.join(BACKEND_DIR, "uploads")
    assert upload_dir_with_env(None) == expected


def test_upload_dir_follows_env(tmp_path):
    """Именно этим переменная и включает том на Railway."""
    target = tmp_path / "том" / "uploads"
    assert upload_dir_with_env(str(target)) == str(target)
    assert target.is_dir(), "каталог должен создаваться, если его ещё нет"


def test_blank_env_falls_back_to_default():
    """Пустая переменная — это «не задано», а не «складывать в корень»."""
    assert upload_dir_with_env("   ") == os.path.join(BACKEND_DIR, "uploads")


def test_uploaded_file_lands_in_upload_dir(client, admin_token):
    """Файл кладётся именно туда, куда указывает UPLOAD_DIR."""
    from utils import UPLOAD_DIR, upload_filename

    r = client.post(
        "/api/upload",
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 32), "image/png")},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert os.path.isfile(os.path.join(UPLOAD_DIR, upload_filename(r.json()["url"])))


def test_storage_check_rejects_unwritable_dir(monkeypatch, tmp_path):
    """Недоступный для записи каталог должен ронять старт, а не первую загрузку."""
    import main

    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    monkeypatch.setattr(main, "UPLOAD_DIR", str(locked))
    try:
        try:
            main.check_upload_storage()
        except RuntimeError as e:
            assert "недоступен для записи" in str(e)
        else:
            raise AssertionError("падение ожидалось")
    finally:
        locked.chmod(0o700)


def test_storage_check_passes_on_normal_dir():
    import main

    main.check_upload_storage()
