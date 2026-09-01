import os
import shutil
import tempfile
import uuid

import ffmpeg

from app.config import settings
from app.services.media_type import detect_media_type


class FileTooLargeError(Exception):
    pass


class UnsupportedMediaError(Exception):
    pass


class DurationExceededError(Exception):
    pass


def _probe_duration(path: str) -> float:
    try:
        probe = ffmpeg.probe(path)
        return float(probe["format"]["duration"])
    except Exception as exc:
        raise RuntimeError(f"Could not read duration: {exc}") from exc


def store_upload(file_obj, filename: str) -> tuple[str, str, float | None]:
    """
    Stream file_obj to a temp path, validate size/type/duration,
    then move to permanent storage.

    Returns (storage_path, media_type_value, duration_seconds_or_None).
    Raises FileTooLargeError, UnsupportedMediaError, DurationExceededError.
    """
    os.makedirs(settings.upload_storage_path, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=settings.upload_storage_path)
    try:
        total = 0
        header_bytes = b""
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds {settings.max_upload_size_bytes} bytes"
                    )
                if len(header_bytes) < 8192:
                    header_bytes += chunk
                tmp_file.write(chunk)

        media_type = detect_media_type(header_bytes, filename)
        if media_type is None:
            raise UnsupportedMediaError(f"Unsupported file type: {filename}")

        duration = _probe_duration(tmp_path)
        if duration > settings.max_upload_duration_seconds:
            raise DurationExceededError(
                f"Duration {duration:.0f}s exceeds limit {settings.max_upload_duration_seconds:.0f}s"
            )

        dest_filename = f"{uuid.uuid4()}{os.path.splitext(filename)[1].lower()}"
        dest_path = os.path.join(settings.upload_storage_path, dest_filename)
        shutil.move(tmp_path, dest_path)
        return dest_path, media_type.value, duration

    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
