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
# requirements.txt is generated from requirements.in via pip-compile (pip-tools).
# To regenerate after editing requirements.in:
#   docker run --rm -v "$(pwd)/backend:/app" python:3.11-slim \
#     bash -c "pip install pip-tools && pip-compile requirements.in --output-file requirements.txt"
#
# Retry up to 3 times; fall back to source build on third attempt to handle
# transient binary-wheel download failures from PyPI CDN.
RUN for attempt in 1 2 3; do \
      if [ "$attempt" -lt 3 ]; then \
        pip install --no-cache-dir --prefer-binary -r requirements.txt && break; \
      else \
        pip install --no-cache-dir -r requirements.txt && break; \
      fi; \
      echo "pip install attempt $attempt failed, retrying..."; \
      sleep 5; \
    done

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
