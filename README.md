# InterScribe

AI-powered audio/video editor for interview workflows. Upload a recording, get a diarized transcript, review narrative clusters, extract and edit quotes, and condense headlines — all running locally.

**Pipeline:**
1. Upload audio/video → WhisperX transcribes + diarizes speakers
2. Review transcript, fix low-confidence words, assign speaker roles
3. Qwen3.5:9b extracts narrative themes and notable moments
4. Review and rank themes; Qwen extracts candidate quotes grounded to transcript segments
5. Review quotes; Qwen condenses approved headlines to ≤20 words

Everything runs on your own hardware. No cloud APIs required after setup.

---

## Platform Support

| Platform | Transcription (WhisperX) | LLM (Qwen / Ollama) |
|---|---|---|
| Linux + NVIDIA GPU | GPU (fast) | GPU in Docker |
| Windows + NVIDIA GPU | GPU (fast) | GPU in Docker (via WSL2) |
| Mac (Apple Silicon) | CPU in Docker (slow) | Metal GPU, run natively |

---

## Quick Install

**The only prerequisite you need to install manually is [Docker Desktop](https://www.docker.com/products/docker-desktop/).** Everything else (Ollama, NVIDIA Container Toolkit, model downloads) is handled by the setup script.

You'll also need a [HuggingFace](https://huggingface.co) token — the script will prompt you and tell you where to get one.

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
./setup.sh
```

The script detects your OS:
- **Mac** — installs Ollama via Homebrew, starts it natively (Metal GPU), sets CPU mode for WhisperX in Docker
- **Linux** — installs NVIDIA Container Toolkit automatically if an NVIDIA GPU is found
- **Windows** — run the above inside your WSL2 terminal (see Windows notes below)

Then open http://localhost:3002.

---

## Windows Notes

Before running `setup.sh` on Windows:

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) with the WSL2 backend enabled
2. Install WSL2 — open PowerShell as Administrator and run `wsl --install`, then reboot
3. Install [NVIDIA drivers for Windows](https://www.nvidia.com/Download/index.aspx) (on Windows, not inside WSL)

Then open your WSL2 terminal (e.g. Ubuntu from the Start menu) and run:

```bash
git clone https://github.com/TJM-NZ/InterScribe.git
cd InterScribe
./setup.sh
```

The script handles the NVIDIA Container Toolkit install inside WSL2. Access the app at http://localhost:3002 in your Windows browser.

---

## First-Run Download Sizes

The script pulls these automatically. Expect 15–30 minutes depending on your connection.

| Component | Size | When |
|---|---|---|
| Qwen3.5:9b (Ollama) | ~6 GB | During `setup.sh` |
| WhisperX `large-v2` (Linux/Windows) | ~3 GB | First transcription job |
| WhisperX `small` (Mac) | ~500 MB | First transcription job |
| pyannote diarization models | ~1 GB | First transcription job |

All models are cached in Docker volumes (or Ollama's local store on Mac) and don't re-download on restart.

---

## Usage

1. Open http://localhost:3002 and upload an audio or video file (up to 2 GB / 3 hours)
2. The worker transcribes it in the background — progress shown in the UI
3. **Gate 1:** Review the transcript, correct low-confidence words (highlighted in amber), and assign speaker roles (interviewer / interviewee)
4. **Gate 2:** Review narrative themes and notable moments extracted by Qwen; reject any that don't fit
5. **Gate 3:** Review extracted quotes grounded to the transcript; approve or discard
6. **Gate 4:** Edit Qwen-condensed headlines (≤20 words) for approved headline-type quotes

---

## Logs

```bash
docker compose logs -f worker    # transcription + LLM jobs
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Stopping

```bash
docker compose down              # stop containers, keep volumes (data preserved)
docker compose down -v           # stop and delete all data
```

---

<details>
<summary>Manual setup (without the script)</summary>

### HuggingFace

1. Create a [HuggingFace account](https://huggingface.co/join)
2. Accept the license for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Accept the license for [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
4. Generate a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (read access)

### Linux (NVIDIA GPU)

```bash
# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

# Verify
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi

# Clone and configure
git clone https://github.com/TJM-NZ/InterScribe.git && cd InterScribe
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, DATABASE_URL, HUGGINGFACE_TOKEN

# Start
docker compose up --build -d
docker compose exec ollama ollama pull qwen3.5:9b
```

### Windows (NVIDIA GPU, via WSL2)

Same as Linux above, but run everything inside your WSL2 terminal. NVIDIA drivers must be installed on Windows first (not in WSL).

After installing NVIDIA Container Toolkit inside WSL2, restart Docker Desktop.

### Mac (Apple Silicon)

```bash
# Install and start Ollama natively (uses Metal GPU)
brew install ollama
ollama pull qwen3.5:9b   # Ollama app starts automatically; or run 'ollama serve &' first

# Clone and configure
git clone https://github.com/TJM-NZ/InterScribe.git && cd InterScribe
cp .env.example .env
# Edit .env and set:
#   POSTGRES_PASSWORD, DATABASE_URL, HUGGINGFACE_TOKEN
#   WHISPER_DEVICE=cpu
#   WHISPER_COMPUTE_TYPE=int8
#   WHISPER_MODEL_SIZE=small
#   OLLAMA_BASE_URL=http://host.docker.internal:11434

# Start (Mac override removes the ollama container and NVIDIA GPU requirements)
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build -d
```

</details>
