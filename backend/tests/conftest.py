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
from app.main import app  # noqa: E402

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def reset_db():
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
