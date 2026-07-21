#!/usr/bin/env bash
set -euo pipefail

# ── Detect platform ────────────────────────────────────────────────────────────
OS="linux"
if [[ "${OSTYPE:-}" == "darwin"* ]]; then
    OS="mac"
fi

echo ""
echo "InterScribe setup (platform: $OS)"
echo "────────────────────────────────"

# ── Docker check ───────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo ""
    echo "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run this script."
    exit 1
fi

if ! docker info &>/dev/null; then
    echo ""
    echo "Docker is installed but not running. Start Docker Desktop and re-run this script."
    exit 1
fi

# ── Mac: Ollama native install ─────────────────────────────────────────────────
if [[ "$OS" == "mac" ]]; then
    if ! command -v brew &>/dev/null; then
        echo ""
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    if ! command -v ollama &>/dev/null; then
        echo "Installing Ollama..."
        brew install ollama
    else
        echo "Ollama already installed."
    fi

    # Start Ollama if not already listening
    if ! curl -sf http://localhost:11434 &>/dev/null; then
        echo "Starting Ollama..."
        ollama serve &>/dev/null &
        OLLAMA_PID=$!
        for i in {1..15}; do
            if curl -sf http://localhost:11434 &>/dev/null; then break; fi
            sleep 1
        done
        if ! curl -sf http://localhost:11434 &>/dev/null; then
            echo "Ollama failed to start. Check 'ollama serve' manually and re-run."
            exit 1
        fi
    else
        echo "Ollama already running."
    fi
fi

# ── Linux: NVIDIA Container Toolkit ───────────────────────────────────────────
if [[ "$OS" == "linux" ]]; then
    if command -v nvidia-smi &>/dev/null; then
        if ! command -v nvidia-ctk &>/dev/null; then
            echo "NVIDIA GPU detected. Installing NVIDIA Container Toolkit..."
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
              | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
              | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
              | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

            sudo apt-get update -qq
            sudo apt-get install -y nvidia-container-toolkit
            sudo nvidia-ctk runtime configure --runtime=docker
            sudo systemctl restart docker
            echo "NVIDIA Container Toolkit installed."
        else
            echo "NVIDIA Container Toolkit already installed."
        fi
    else
        echo "No NVIDIA GPU detected — transcription will run on CPU (slow)."
    fi
fi

# ── .env setup ─────────────────────────────────────────────────────────────────
if [[ -f .env ]]; then
    echo ""
    echo ".env already exists — skipping configuration. Delete it and re-run to reconfigure."
else
    cp .env.example .env

    echo ""
    echo "HuggingFace token required for speaker diarization."
    echo "  1. Create an account at https://huggingface.co/join"
    echo "  2. Accept the license at https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo "  3. Accept the license at https://huggingface.co/pyannote/segmentation-3.0"
    echo "  4. Generate a token at https://huggingface.co/settings/tokens (read access)"
    echo ""
    read -rp "Enter your HuggingFace token: " HF_TOKEN

    PG_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")

    python3 - <<PYEOF
import re

with open('.env') as f:
    env = f.read()

env = env.replace('POSTGRES_PASSWORD=changeme', 'POSTGRES_PASSWORD=${PG_PASSWORD}')
env = env.replace(
    'DATABASE_URL=postgresql://interscribe:changeme@postgres:5432/interscribe',
    'DATABASE_URL=postgresql://interscribe:${PG_PASSWORD}@postgres:5432/interscribe'
)
env = env.replace('HUGGINGFACE_TOKEN=hf_your_token_here', 'HUGGINGFACE_TOKEN=${HF_TOKEN}')

if '${OS}' == 'mac':
    env = env.replace('WHISPER_DEVICE=cuda', 'WHISPER_DEVICE=cpu')
    env = env.replace('WHISPER_COMPUTE_TYPE=float16', 'WHISPER_COMPUTE_TYPE=int8')
    env = env.replace('WHISPER_MODEL_SIZE=large-v2', 'WHISPER_MODEL_SIZE=small')
    env = env.replace('OLLAMA_BASE_URL=http://ollama:11434', 'OLLAMA_BASE_URL=http://host.docker.internal:11434')

with open('.env', 'w') as f:
    f.write(env)
PYEOF

    echo ".env written."
fi

# ── Start stack ────────────────────────────────────────────────────────────────
echo ""
echo "Building and starting containers (this may take a few minutes on first run)..."
if [[ "$OS" == "mac" ]]; then
    docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build -d
else
    docker compose up --build -d
fi

# ── Pull Qwen model ────────────────────────────────────────────────────────────
echo ""
echo "Pulling Qwen3.5:9b (~6 GB) — this may take a while..."
if [[ "$OS" == "mac" ]]; then
    ollama pull qwen3.5:9b
else
    # Wait for ollama container to be healthy
    echo "Waiting for Ollama to be ready..."
    for i in {1..30}; do
        if docker compose exec ollama ollama list &>/dev/null; then break; fi
        sleep 2
    done
    docker compose exec ollama ollama pull qwen3.5:9b
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────"
echo "InterScribe is running."
echo ""
echo "  Frontend:  http://localhost:3002"
echo "  API docs:  http://localhost:8002/docs"
echo ""
echo "First transcription will also download WhisperX models (~1-4 GB, cached)."
echo "────────────────────────────────"
