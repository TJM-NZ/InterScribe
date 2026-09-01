import magic

from app.models.video import MediaType

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def detect_media_type(file_bytes: bytes, filename: str) -> MediaType | None:
    """Return MediaType based on MIME sniffing, with extension as fallback."""
    mime = magic.from_buffer(file_bytes, mime=True)
    if mime.startswith("audio/"):
        return MediaType.audio
    if mime.startswith("video/"):
        return MediaType.video

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in AUDIO_EXTENSIONS:
        return MediaType.audio
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video

    return None
