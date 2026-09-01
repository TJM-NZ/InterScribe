<<<<<<< Updated upstream
import os
import struct
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# --- env setup BEFORE any app import ---
_base_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://interscribe:interscribe@postgres:5432/interscribe",
)
TEST_DATABASE_URL = _base_url.rsplit("/", 1)[0] + "/interscribe_test"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("WHISPER_MODEL_SIZE", "tiny")
os.environ.setdefault("WHISPER_COMPUTE_TYPE", "int8")
os.environ.setdefault("WHISPER_BATCH_SIZE", "4")
os.environ.setdefault("WHISPER_MODEL_CACHE", tempfile.mkdtemp())
os.environ.setdefault("HF_HOME", tempfile.mkdtemp())
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024 * 1024))
os.environ.setdefault("MAX_UPLOAD_DURATION_SECONDS", "10800")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QWEN_MODEL", "qwen3.5:9b")
os.environ.setdefault("NARRATIVE_CLUSTER_THRESHOLD", "0.3")
os.environ.setdefault("NARRATIVE_TOP_N", "5")
os.environ.setdefault("NARRATIVE_CHUNK_MAX_TOKENS", "10000")
os.environ.setdefault("NARRATIVE_CHUNK_RETRIES", "3")
os.environ.setdefault("PHASE2_OVERLAP_TURNS", "2")
os.environ.setdefault("PHASE2_DEDUP_OVERLAP_RATIO", "0.5")
os.environ.setdefault("PHASE2_DEDUP_TEXT_SIMILARITY", "0.85")

# Create test database (drop + recreate for a clean slate each run)
_admin_url = _base_url.rsplit("/", 1)[0] + "/postgres"
_admin_engine = create_engine(_admin_url, isolation_level="AUTOCOMMIT")
with _admin_engine.connect() as _conn:
    _conn.execute(text("DROP DATABASE IF EXISTS interscribe_test"))
    _conn.execute(text("CREATE DATABASE interscribe_test"))
_admin_engine.dispose()

# Safe to import app now — settings picks up TEST_DATABASE_URL
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
import app.models.video  # noqa: F401, E402
import app.models.phase1  # noqa: F401, E402
import app.models.phase2  # noqa: F401, E402
from app.main import app  # noqa: E402

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def reset_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(tmp_path):
    settings.upload_storage_path = str(tmp_path)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_fake_audio(size: int = 1024) -> bytes:
    """Minimal WAV header + silence."""
    channels = 1
    sample_rate = 16000
    bits_per_sample = 16
    data_size = size
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16, 1, channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + b"\x00" * data_size


def make_video(db, status=None):
    """Create and flush a Video row. Caller is responsible for commit."""
    from datetime import datetime, timezone
    from app.models.video import JobStatus, MediaType, Video

    v = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=status or JobStatus.uploaded,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def make_segment(db, video_id, seg_id, speaker="SPEAKER_00", text=None, confidence=0.9):
    """Add a TranscriptSegment row and flush it."""
    from app.models.video import TranscriptSegment

    s = TranscriptSegment(
        video_id=video_id,
        segment_id=seg_id,
        start_ts=float(seg_id),
        end_ts=float(seg_id + 1),
        text=text if text is not None else f"Utterance {seg_id}",
        speaker_label=speaker,
        confidence=confidence,
    )
    db.add(s)
    db.flush()
    return s


def seed_video_with_segments(db, speakers=None, status=None):
    """Helper: create a reviewed video with segments and speaker role maps."""
    from datetime import datetime, timezone
    from app.models.video import JobStatus, MediaType, SpeakerRoleMap, TranscriptSegment, Video

    _status = status or JobStatus.ready_for_review
    video = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=_status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.flush()

    _speakers = speakers or ["SPEAKER_00", "SPEAKER_01"]
    for idx, label in enumerate(_speakers):
        db.add(TranscriptSegment(
            video_id=video.id,
            segment_id=idx,
            start_ts=float(idx),
            end_ts=float(idx + 1),
            text=f"Utterance {idx} from {label}",
            speaker_label=label,
            confidence=0.9,
        ))
        db.add(SpeakerRoleMap(
            video_id=video.id,
            speaker_label=label,
            role="interviewer" if idx == 0 else "interviewee",
        ))

    db.commit()
    db.refresh(video)
    return video
=======
import os
import struct
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# --- env setup BEFORE any app import ---
_base_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://interscribe:interscribe@postgres:5432/interscribe",
)
TEST_DATABASE_URL = _base_url.rsplit("/", 1)[0] + "/interscribe_test"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("WHISPER_MODEL_SIZE", "tiny")
os.environ.setdefault("WHISPER_COMPUTE_TYPE", "int8")
os.environ.setdefault("WHISPER_BATCH_SIZE", "4")
os.environ.setdefault("WHISPER_MODEL_CACHE", tempfile.mkdtemp())
os.environ.setdefault("HUGGINGFACE_TOKEN", "test-token")
os.environ.setdefault("HF_HOME", tempfile.mkdtemp())
os.environ.setdefault("MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024 * 1024))
os.environ.setdefault("MAX_UPLOAD_DURATION_SECONDS", "10800")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("QWEN_MODEL", "qwen3.5:9b")
os.environ.setdefault("NARRATIVE_CLUSTER_THRESHOLD", "0.3")
os.environ.setdefault("NARRATIVE_TOP_N", "5")
os.environ.setdefault("NARRATIVE_CHUNK_MAX_TOKENS", "10000")
os.environ.setdefault("NARRATIVE_CHUNK_RETRIES", "3")
os.environ.setdefault("PHASE2_OVERLAP_TURNS", "2")
os.environ.setdefault("PHASE2_DEDUP_OVERLAP_RATIO", "0.5")
os.environ.setdefault("PHASE2_DEDUP_TEXT_SIMILARITY", "0.85")

# Create test database (drop + recreate for a clean slate each run)
_admin_url = _base_url.rsplit("/", 1)[0] + "/postgres"
_admin_engine = create_engine(_admin_url, isolation_level="AUTOCOMMIT")
with _admin_engine.connect() as _conn:
    _conn.execute(text("DROP DATABASE IF EXISTS interscribe_test"))
    _conn.execute(text("CREATE DATABASE interscribe_test"))
_admin_engine.dispose()

# Safe to import app now — settings picks up TEST_DATABASE_URL
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
import app.models.video  # noqa: F401, E402
import app.models.phase1  # noqa: F401, E402
import app.models.phase2  # noqa: F401, E402
from app.main import app  # noqa: E402

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def reset_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(tmp_path):
    settings.upload_storage_path = str(tmp_path)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_fake_audio(size: int = 1024) -> bytes:
    """Minimal WAV header + silence."""
    channels = 1
    sample_rate = 16000
    bits_per_sample = 16
    data_size = size
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16, 1, channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + b"\x00" * data_size


def make_video(db, status=None):
    """Create and flush a Video row. Caller is responsible for commit."""
    from datetime import datetime, timezone
    from app.models.video import JobStatus, MediaType, Video

    v = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=status or JobStatus.uploaded,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def make_segment(db, video_id, seg_id, speaker="SPEAKER_00", text=None, confidence=0.9):
    """Add a TranscriptSegment row and flush it."""
    from app.models.video import TranscriptSegment

    s = TranscriptSegment(
        video_id=video_id,
        segment_id=seg_id,
        start_ts=float(seg_id),
        end_ts=float(seg_id + 1),
        text=text if text is not None else f"Utterance {seg_id}",
        speaker_label=speaker,
        confidence=confidence,
    )
    db.add(s)
    db.flush()
    return s


def seed_video_with_segments(db, speakers=None, status=None):
    """Helper: create a reviewed video with segments and speaker role maps."""
    from datetime import datetime, timezone
    from app.models.video import JobStatus, MediaType, SpeakerRoleMap, TranscriptSegment, Video

    _status = status or JobStatus.ready_for_review
    video = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=_status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.flush()

    _speakers = speakers or ["SPEAKER_00", "SPEAKER_01"]
    for idx, label in enumerate(_speakers):
        db.add(TranscriptSegment(
            video_id=video.id,
            segment_id=idx,
            start_ts=float(idx),
            end_ts=float(idx + 1),
            text=f"Utterance {idx} from {label}",
            speaker_label=label,
            confidence=0.9,
        ))
        db.add(SpeakerRoleMap(
            video_id=video.id,
            speaker_label=label,
            role="interviewer" if idx == 0 else "interviewee",
        ))

    db.commit()
    db.refresh(video)
    return video
>>>>>>> Stashed changes
