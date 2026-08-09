FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    libgomp1 \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libavdevice-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Download pyannote models at build time — no token or network needed at runtime
ENV HF_HOME=/models/hf
RUN --mount=type=secret,id=hf_token \
    python -c "
token = open('/run/secrets/hf_token').read().strip()
from huggingface_hub import snapshot_download
snapshot_download('pyannote/speaker-diarization-3.1', token=token)
snapshot_download('pyannote/segmentation-3.0', token=token)
"

COPY alembic.ini .
COPY migrations/ migrations/
COPY app/ app/
COPY tests/ tests/
